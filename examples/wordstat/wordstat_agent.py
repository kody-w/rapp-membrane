"""WordStat — line/word/char counts and the most common words in a text file.

Ported from wordstat.py (a CLI) into a single-file RAPP agent by the membrane.
The port preserves BEHAVIOUR, not shape: the original printed a report to
stdout; this returns the same facts as structured data AND the same rendered
report, so parity can be asserted on the facts rather than on formatting.
"""

import collections
import json
import re
import sys

try:
    from agents.basic_agent import BasicAgent
except ImportError:  # standalone — no brainstem required
    class BasicAgent:
        def __init__(self, name=None, metadata=None):
            if name:
                self.name = name
            if metadata:
                self.metadata = metadata

        def perform(self, **kwargs):
            return "Not implemented."

        def to_tool(self):
            return {"type": "function", "function": {
                "name": self.name,
                "description": self.metadata.get("description", ""),
                "parameters": self.metadata.get("parameters", {})}}


# Lifted verbatim from the original so the counting cannot drift away from it.
def analyse(text, top=3):
    words = re.findall(r"[a-z']+", text.lower())
    common = collections.Counter(words).most_common(top)
    return {"lines": len(text.splitlines()), "words": len(words),
            "chars": len(text), "top": common}


class WordStatAgent(BasicAgent):
    def __init__(self):
        self.name = "WordStat"
        self.metadata = {
            "name": self.name,
            "description": ("Report line, word and character counts plus the N "
                            "most common words in a text file."),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string",
                             "description": "Path to the text file to analyse."},
                    "top": {"type": "integer",
                            "description": "How many most-common words to return. Default 3."},
                },
                "required": ["path"],
            },
        }
        super().__init__(name=self.name, metadata=self.metadata)

    def perform(self, **kwargs):
        path = kwargs.get("path")
        if not path:
            return json.dumps({"status": "error", "message": "path is required"})
        try:
            top = int(kwargs.get("top", 3) or 3)
        except (TypeError, ValueError):
            return json.dumps({"status": "error", "message": "top must be an integer"})
        try:
            text = open(path, encoding="utf-8").read()
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

        r = analyse(text, top)
        # The original's exact stdout, kept so parity is directly checkable.
        report = f"lines={r['lines']} words={r['words']} chars={r['chars']}\n"
        report += "".join(f"  {w}: {c}\n" for w, c in r["top"])
        return json.dumps({"status": "ok", "lines": r["lines"], "words": r["words"],
                           "chars": r["chars"],
                           "top": [{"word": w, "count": c} for w, c in r["top"]],
                           "report": report.rstrip("\n")}, indent=2)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--tool":
        print(json.dumps(WordStatAgent().to_tool(), indent=2))
    else:
        raw = a[0] if a else (sys.stdin.read().strip() or "{}")
        print(WordStatAgent().perform(**json.loads(raw)))
