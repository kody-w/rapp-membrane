#!/usr/bin/env python3
"""wordstat — count words, lines and the top-N most common words in a text file."""
import sys, collections, re

def analyse(text, top=3):
    words = re.findall(r"[a-z']+", text.lower())
    common = collections.Counter(words).most_common(top)
    return {"lines": len(text.splitlines()), "words": len(words),
            "chars": len(text), "top": common}

def main():
    if len(sys.argv) < 2:
        print("usage: wordstat <file> [topN]"); return 1
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    text = open(sys.argv[1], encoding="utf-8").read()
    r = analyse(text, top)
    print(f"lines={r['lines']} words={r['words']} chars={r['chars']}")
    for w, c in r["top"]:
        print(f"  {w}: {c}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
