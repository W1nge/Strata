// test_tiered_win.cpp - the Windows TieredExpertSource against a fake pack.
// Validates, without model weights: open (view + reservation), the cache fill (cold reads through the view),
// settle's three tiers, blob()/pinned()/device_alias() dispatch, read_into's FILE_FLAG_NO_BUFFERING path,
// and begin_layer's prefetch queue.
#include "strata/core/expert_source.hpp"
#include "strata/core/expert_cache.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"

#include <cuda_runtime.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>

#include <cstdio>
#include <filesystem>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
#include <thread>
#include <atomic>

using namespace strata::core;

static const int64_t L = 4, E = 8;
static const uint64_t BLOB = 1382400;

static void make_blob(uint8_t* p, int64_t l, int64_t e) {
    // deterministic per-blob pattern: a 64-byte tag repeated through the blob
    char tag[64];
    std::snprintf(tag, sizeof tag, "BLOB L%lld E%lld checksum %08x", (long long) l, (long long) e,
                  (unsigned) (l * 1000 + e));
    std::memset(p, (uint8_t) ((l * 31 + e * 7) | 1), BLOB);   // deterministic filler, no stack garbage
    std::memcpy(p, tag, std::strlen(tag) + 1);
}

static bool expect(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    return ok;
}

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    int failures = 0;
    const std::string pack = "test-pack";
    std::filesystem::create_directories(pack);

    // ---- the fake pack: no native_experts.txt -> non-native layout, total = L*E*BLOB
    std::printf("== 1. the fake pack ==\n");
    {
        std::string err;
        if (!strata::kernels::cpu::expert_layout_load(pack, L, E, err)) {
            std::printf("layout load failed: %s\n", err.c_str());
            return 1;
        }
        const auto& lay = strata::kernels::cpu::expert_layout();
        std::ofstream f(pack + "/experts.bin", std::ios::binary);
        std::vector<uint8_t> blob(BLOB);
        for (int64_t l = 0; l < L; ++l)
            for (int64_t e = 0; e < E; ++e) {
                make_blob(blob.data(), l, e);
                f.write((const char*) blob.data(), (std::streamsize) BLOB);
            }
        expect((uint64_t) lay.total == (uint64_t) L * E * BLOB, "layout total matches L*E*BLOB");
    }

    // ---- 2. open
    std::printf("== 2. open ==\n");
    std::string err;
    TieredExpertSource src;
    const bool opened = src.open(pack, L, E, err);
    failures += !expect(opened, (std::string("open: ") + err).c_str());
    failures += !expect(src.blob(0, 0) != nullptr, "blob(0,0) mapped");
    failures += !expect(!src.dma_capable(0), "unsettled file mapping has no DMA tier");

    // ---- 3. the cache fill: three experts resident in VRAM (engine-style startup)
    std::printf("== 3. the cache fill ==\n");
    ExpertCache cache;
    failures += !expect(cache.open(3, L, E, (int64_t) BLOB, err), "cache.open(3 slots)");
    const std::pair<int64_t, int64_t> cached[] = {{0, 0}, {1, 3}, {2, 7}};
    for (auto [l, e] : cached) {
        const int32_t slot = cache.admit(l, e);
        failures += !expect(slot >= 0, "admit(l,e)");
        failures += !expect(cache.fill_slot_blocking(slot, src.blob(l, e), err), "fill_slot_blocking");
    }

    // ---- 4. settle: profile ranks 4 more experts into the pinned tier (explicit budget)
    std::printf("== 4. settle ==\n");
    std::vector<std::pair<int32_t, int32_t>> profile;
    for (auto [l, e] : cached) profile.push_back({(int32_t) l, (int32_t) e});
    const std::pair<int64_t, int64_t> pinned_want[] = {{0, 1}, {1, 2}, {2, 4}, {3, 5}};
    for (auto [l, e] : pinned_want) profile.push_back({(int32_t) l, (int32_t) e});
    const int64_t budget = 4 * (int64_t) BLOB;   // exactly the four profile picks past the cache
    const bool settled = src.settle(&cache, profile, budget, /*reserve=*/0, /*threads=*/4, err);
    failures += !expect(settled, (std::string("settle: ") + err).c_str());
    std::printf("  note: %s\n", src.note().c_str());
    for (int64_t l = 0; l < L; ++l)
        failures += !expect(src.dma_capable(l), "Windows pinned arena enables DMA planning");
    failures += !expect(!src.dma_capable(-1) && !src.dma_capable(L), "invalid layer cannot plan DMA");

    // ---- 5. tier dispatch
    std::printf("== 5. tiers ==\n");
    for (auto [l, e] : cached) {
        failures += !expect(!src.pinned(l, e), "cache resident is NOT pinned (it is VRAM tier)");
    }
    for (auto [l, e] : pinned_want) {
        failures += !expect(src.pinned(l, e), "profile pick IS pinned");
        failures += !expect(src.device_alias(l, e) != nullptr, "device_alias non-null for pinned");
        failures += !expect(src.blob(l, e) >= src.blob(0, 0) + (uint64_t) L * E * BLOB ||
                                src.blob(l, e) < src.blob(0, 0),
                            "pinned blob lives in the arena, outside the view");
    }
    const std::pair<int64_t, int64_t> cold = {3, 6};   // never in the profile: cold
    failures += !expect(!src.pinned(cold.first, cold.second), "unranked pair is cold");
    failures += !expect(src.device_alias(cold.first, cold.second) == nullptr, "no device alias for cold");

    // ---- 6. content: every tier serves the bytes that were written
    std::printf("== 6. contents ==\n");
    std::vector<uint8_t> want(BLOB), got(BLOB);
    auto check_blob = [&](int64_t l, int64_t e, const char* what) {
        make_blob(want.data(), l, e);
        const uint8_t* p = src.blob(l, e);
        bool ok = p != nullptr && std::memcmp(p, want.data(), BLOB) == 0;
        if (!ok && p != nullptr) {
            size_t d = 0;
            while (d < BLOB && p[d] == want[d]) ++d;
            std::printf("    diff at %zu: got %02x %02x %02x want %02x %02x %02x | ptr-ptr0 %lld\n", d, p[d],
                        p[d + 1], p[d + 2], want[d], want[d + 1], want[d + 2],
                        (long long) (p - src.blob(0, 0)));
        }
        failures += !expect(ok, what);
    };
    check_blob(0, 0, "VRAM-tier blob bytes (through the view)");
    check_blob(0, 1, "PINNED-tier blob bytes (from the arena)");
    check_blob(3, 6, "COLD-tier blob bytes (through the view)");

    // A working-set hint must remove an interior page without changing the mapped bytes.
    const uint8_t* view = src.blob(0, 0);
    PSAPI_WORKING_SET_EX_INFORMATION wi{};
    wi.VirtualAddress = (void*) (view + 8192);
    QueryWorkingSetEx(GetCurrentProcess(), &wi, sizeof wi);
    failures += !expect(wi.VirtualAttributes.Valid != 0, "checked view page is resident");
    src.release_host_copy(0, 0);
    QueryWorkingSetEx(GetCurrentProcess(), &wi, sizeof wi);
    failures += !expect(wi.VirtualAttributes.Valid == 0, "redundant view page removed from working set");
    check_blob(0, 0, "trimmed view bytes remain intact on reread");

    // ---- 7. read_into: the streamed path (a cold blob through FILE_FLAG_NO_BUFFERING) and memcpy (pinned)
    std::printf("== 7. read_into ==\n");
    {
        make_blob(want.data(), 3, 6);
        src.read_into(src.blob(3, 6), got.data(), BLOB);
        failures += !expect(std::memcmp(got.data(), want.data(), BLOB) == 0, "read_into(cold) via direct I/O");
        make_blob(want.data(), 0, 1);
        src.read_into(src.blob(0, 1), got.data(), BLOB);
        failures += !expect(std::memcmp(got.data(), want.data(), BLOB) == 0, "read_into(pinned) via memcpy");
        // a partial read from the middle of a cold blob (offset not sector-aligned): the bounce-buffer path
        make_blob(want.data(), 3, 6);
        src.read_into(src.blob(3, 6) + 12345, got.data(), 777777);
        failures += !expect(std::memcmp(got.data(), want.data() + 12345, 777777) == 0,
                            "read_into(cold, unaligned middle) bounce path");
    }

    // Both stream and cached reads: all tiers, unaligned partial ranges, and the end of the file.
    for (int cached_read = 0; cached_read < 2; ++cached_read) {
        std::vector<const uint8_t*> ptrs;
        for (int64_t l = 0; l < L; ++l) for (int64_t e = 0; e < E; ++e) ptrs.push_back(src.blob(l, e));
        std::atomic<bool> good{true};
        std::vector<std::thread> readers;
        for (int t = 0; t < 8; ++t) readers.emplace_back([&, t] {
            std::vector<uint8_t> expected(BLOB), actual(BLOB);
            for (int i = 0; i < L * E; ++i) {
                const int at = (i * 7 + t) % (L * E);
                make_blob(expected.data(), at / E, at % E);
                const size_t off = i % 3 == 1 ? 12345 : i % 3 == 2 ? BLOB - 101 : 0;
                const size_t n = i % 3 == 1 ? 777777 : i % 3 == 2 ? 101 : BLOB;
                if (cached_read) src.read_into_cached(ptrs[(size_t) at] + off, actual.data(), n);
                else src.read_into(ptrs[(size_t) at] + off, actual.data(), n);
                if (std::memcmp(actual.data(), expected.data() + off, n)) good.store(false);
            }
        });
        for (auto& t : readers) t.join();
        failures += !expect(good.load(), cached_read ? "256 concurrent cached full/partial reads, exact bytes"
                                                   : "256 concurrent stream full/partial reads, exact bytes");
    }

    // ---- 8. begin_layer prefetch of cold experts (just: no crash, counter moves)
    std::printf("== 8. begin_layer prefetch ==\n");
    {
        const int64_t before = src.cold_prefetches();
        const int32_t ids[] = {6, 6, 7};
        src.begin_layer(3, ids, 3);
        src.begin_layer(3, ids, 3);   // second pass: the queued range repeats, still must not crash
        failures += !expect(src.cold_prefetches() == before + 4, "duplicate expert prefetched once per call");
        std::vector<int32_t> res((size_t) L * E, kNotResident);
        for (auto [l, e] : cached) res[(size_t) l * E + e] = 0;
        res[3 * E + 6] = 1;  // an originally cold expert was promoted by adaptive residency
        src.set_residency(res.data());
        const int64_t promoted = src.cold_prefetches();
        src.begin_layer(3, ids, 3);
        failures += !expect(src.cold_prefetches() == promoted + 1, "promoted cold expert is not prefetched");
        res[0] = kNotResident;  // an originally VRAM expert was evicted and now needs CPU pages
        const int32_t evicted[] = {0, 0, 1, -1, (int32_t) E};
        src.begin_layer(0, evicted, 5);
        failures += !expect(src.cold_prefetches() == promoted + 2, "evicted expert prefetched, pinned and invalid skipped");
        src.set_residency(nullptr);
    }

    src.close();
    failures += !expect(!src.dma_capable(0), "closed arena disables DMA planning");
    failures += !expect(src.open(pack, L, E, err), "reopen for zero pinned budget");
    failures += !expect(src.settle(&cache, profile, 0, 0, 4, err), "settle with zero pinned budget");
    failures += !expect(!src.dma_capable(0), "zero pinned budget leaves DMA disabled");

    std::printf("\n%s (%d failures)\n", failures == 0 ? "ALL TIERED-SOURCE TESTS PASSED" : "FAILURES PRESENT",
                failures);
    return failures == 0 ? 0 : 1;
}
