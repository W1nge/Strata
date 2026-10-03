#include "strata/core/expert_cache.hpp"
#include "strata/core/expert_source.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <random>
#include <stdexcept>
#include <vector>

struct Source : strata::core::ExpertSource {
    mutable std::atomic<int> reads_n{0};
    mutable std::atomic<int> cached_n{0};
    bool broken = false;
    const uint8_t* blob(int64_t, int64_t) override { return nullptr; }
    void read_into(const uint8_t* a, uint8_t* b, size_t n) const override {
        ++reads_n;
        if (broken) throw std::runtime_error("injected read failure");
        std::memcpy(b, a, n);
    }
    void read_into_cached(const uint8_t* a, uint8_t* b, size_t n) const override {
        ++cached_n; std::memcpy(b, a, n);
    }
};
int main() {
    using Cache = strata::core::ExpertCache;
    Cache cache; Source source; std::string err;
    const int count = 89;
    std::vector<int64_t> sizes;
    std::vector<std::vector<uint8_t>> host(count);
    std::vector<Cache::SlotFill> jobs;
    const int64_t variety[] = {1, 3, 255, 257, 1025, 65539, 1048593};
    for (int i = 0; i < count; ++i) {
        sizes.push_back(variety[i % 7]); host[i].resize((size_t) sizes.back());
        for (size_t j = 0; j < host[i].size(); ++j) host[i][j] = (uint8_t) (i * 73 + j * 31 + j / 257);
        jobs.push_back({i, host[i].data(), sizes.back()});
    }
    auto require = [&](bool ok, const char* label) {
        if (!ok) { std::fprintf(stderr, "FAIL %s: %s\n", label, err.c_str()); std::exit(1); }
    };
    require(cache.open_sized(sizes, 1, count, err), "open");
    std::mt19937 rng(4726);
    int cases = 0;
    for (int workers : {1, 2, 4, 8}) for (int mode : {0, 1, 2}) for (int pass = 0; pass < 3; ++pass) {
        require(cudaMemset(cache.device_slot(0), 0xA5, (size_t) cache.bytes()) == cudaSuccess, "sentinel");
        auto selected = jobs;
        if (pass == 2) selected.resize(13); // sparse writes must leave all other slots intact
        std::shuffle(selected.begin(), selected.end(), rng);
        const int reads_before = source.reads_n.load();
        const int cached_before = source.cached_n.load();
        require(cache.fill_slots_staged(selected, source, workers, mode, err), "refill");
        require(source.reads_n.load() - reads_before == (mode == 1 ? (int) selected.size() : 0), "source read dispatch");
        require(source.cached_n.load() - cached_before == (mode == 2 ? (int) selected.size() : 0), "cached read dispatch");
        for (int i = 0; i < count; ++i) {
            const size_t capacity = (size_t) ((sizes[i] + 255) / 256 * 256);
            std::vector<uint8_t> got(capacity);
            require(cudaMemcpy(got.data(), cache.device_slot(i), capacity, cudaMemcpyDeviceToHost) == cudaSuccess, "readback");
            for (size_t j = 0; j < capacity; ++j) {
                const bool written = (pass != 2 || i < 13) && j < host[i].size();
                require(got[j] == (written ? host[i][j] : 0xA5), "exact bytes and untouched padding");
            }
        }
        ++cases;
    }
    for (auto invalid : std::vector<std::vector<Cache::SlotFill>>{
             {{-1, host[0].data(), 1}}, {{count, host[0].data(), 1}}, {{0, nullptr, 1}},
             {{0, host[0].data(), 0}}, {{0, host[0].data(), 257}}, {jobs[0], jobs[0]}}) {
        require(!cache.fill_slots_staged(invalid, source, 4, true, err), "reject invalid fill"); ++cases;
    }
    source.broken = true;
    require(!cache.fill_slots_staged(jobs, source, 4, true, err), "propagate read exception"); ++cases;
    source.broken = false;
    require(cache.fill_slots_staged(jobs, source, 4, true, err), "recover after failed read");
    for (const auto& j : jobs) require(cache.verify_slot(j.slot, j.src, err, j.bytes), "recovery bytes"); ++cases;
    require(cache.fill_slots_staged({}, source, 4, true, err), "empty fill"); ++cases;
    std::printf("PASS %d refill cases: exact data, padding, sparse writes, validation and failure cleanup\n", cases);
}
