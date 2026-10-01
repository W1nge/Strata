# bpe_encode.py - byte-level BPE encoder for the exported Qwen tokenizer (pack tokenizer/ dir).
# Usage: python bpe_encode.py <text-file> <pack-tokenizer-dir> <out-ids-file>
# Verified against the engine: "The capital of France is" -> 760,6511,314,9338,369
import json, sys, pathlib
import regex as re

PAT = re.compile(r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+""")

def bytes_to_unicode():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + \
         list(range(ord("\xae"), ord("\xff") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))

def bpe(piece, ranks, cache):
    if piece in cache:
        return cache[piece]
    word = list(piece)
    while len(word) > 1:
        pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
        best = min(pairs, key=lambda p: ranks.get(p, 1 << 30))
        if best not in ranks:
            break
        out, i = [], 0
        while i < len(word):
            if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                out.append(word[i] + word[i + 1])
                i += 2
            else:
                out.append(word[i])
                i += 1
        word = out
    cache[piece] = word
    return word

def main():
    text_path, tok_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    vocab = json.load(open(pathlib.Path(tok_dir) / "vocab.json", encoding="utf-8"))
    ranks = {}
    for i, line in enumerate(open(pathlib.Path(tok_dir) / "merges.txt", encoding="utf-8")):
        if line and not line.startswith("#"):
            a, b = line.rstrip("\n").split(" ")
            ranks[(a, b)] = i
    b2u = bytes_to_unicode()
    u2b = {v: k for k, v in b2u.items()}
    enc = dict(vocab)                               # vocab.json is already token -> id
    cache = {}
    text = open(text_path, encoding="utf-8").read()
    ids = []
    for piece in PAT.findall(text):
        mapped = "".join(b2u[b] for b in piece.encode("utf-8"))
        for tok in bpe(mapped, ranks, cache):
            if tok in enc:
                ids.append(enc[tok])
            else:                                    # fall back to byte tokens
                for ch in tok:
                    ids.append(enc[ch])
    with open(out_path, "w") as f:
        f.write(" ".join(map(str, ids)))
    print(f"{len(ids)} tokens -> {out_path}")

if __name__ == "__main__":
    main()
