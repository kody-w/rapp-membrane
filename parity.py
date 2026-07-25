#!/usr/bin/env python3
"""parity.py — does the port actually do what the original did?

This is the MECHANICAL half of membraning. It makes no decisions and generates
nothing. It takes an original, a port, and a list of cases, runs both, and says
whether the port reproduced the original's observable facts.

    parity.py <original.py> <ported_agent.py> cases.json

    cases.json: [ {"argv": ["file.txt","2"], "args": {"path":"file.txt","top":2}} ]

WHY THIS IS SEPARATE FROM THE SHAPING

Shaping is judgment and must be done by something intelligent that has actually
read the code -- it cannot be a case statement over file extensions, and it
cannot be delegated to a small model with no context. That was tried: a
context-free model handed the task returned prose asking to be shown the file,
then wrote that prose into a .py, which then failed to parse. The lesson is not
"models cannot port code"; it is that the thing doing the shaping must be the
thing holding the context.

So: an agent shapes, and THIS verifies. The verifier does not care who wrote the
port or how many attempts it took. It compares facts, and facts do not
negotiate.

Comparison is on FACTS, not bytes. A port that returns the same numbers in a
different layout is a correct port; demanding byte-identical stdout would reject
good work and teach the shaper to imitate formatting instead of behaviour.
"""
import json, re, subprocess, sys, pathlib


def facts(s):
    """Numbers and name=number / name: number pairs — what the thing computed,
    stripped of how it chose to print it."""
    t = (s or "").lower()
    return set(re.findall(r"[a-z']+\s*[:=]\s*\d+", t)) | set(re.findall(r"\b\d+\b", t))


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"<crashed: {e}>"


def port_output(text):
    """A port may return JSON; if it carries a `report`, compare on that."""
    try:
        d = json.loads(text)
    except Exception:
        return text
    if isinstance(d, dict):
        return d.get("report") or json.dumps(d)
    return text


def main():
    original, ported, cases_file = sys.argv[1], sys.argv[2], sys.argv[3]
    cases = json.load(open(cases_file))
    results, ok = [], True
    for i, c in enumerate(cases, 1):
        og = run([sys.executable, original, *[str(a) for a in c["argv"]]])
        pt = port_output(run([sys.executable, ported, json.dumps(c["args"])]))
        missing = sorted(facts(og) - facts(pt))
        passed = not missing
        ok &= passed
        results.append({"case": i, "passed": passed, "missing_facts": missing[:8]})
        print(f"  case {i}: {'PARITY' if passed else 'MISMATCH ' + str(missing[:6])}")
    print()
    print(json.dumps({"status": "parity" if ok else "no-parity",
                      "cases": len(cases), "results": results}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
