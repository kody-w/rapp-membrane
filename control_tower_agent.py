"""ControlTower — the publishing gate and estate view, as one file.

An agent estate accumulates two problems that nothing in a normal toolchain
watches for:

  1. Content leaves that should not. Secrets and internal names reach public
     repositories, usually inside something nobody re-read: an archived tree, a
     captured session, a vendored copy of a fixed upstream.
  2. Capabilities scatter. Skills and agents pile up across runtimes in shapes
     that cannot see each other, and nothing reports the spread.

This agent is the part of a control tower that is portable. It carries no
estate map, no roster, and no operator identity -- you point it at your own.

    gate          scan a tree for secrets and denylisted names before it ships
    neighborhoods count capabilities per runtime on this machine
    denylist      show how the roster is configured (never its contents)

DESIGN NOTES worth keeping if you fork this

  * The roster is INJECTED, never embedded. A committed list of names you must
    never publish IS the disclosure it exists to prevent. Set $RAPP_DENYLIST to
    a file path, or $RAPP_DENYLIST_TERMS to a comma-separated list.
  * Unconfigured means REFUSE, not allow. A gate that silently passes because
    it has nothing to check reports "clean" precisely when it is checking
    nothing. That failure mode is worse than having no gate, because it is
    trusted.
  * Findings report file and count. Never the matched value. A leak report that
    quotes the secret is a second copy of the leak.
  * Short all-caps tokens match on word boundaries, or an acronym fires inside
    unrelated words and the whole thing gets ignored as noise.
"""

import json
import os
import re
import sys

try:
    from agents.basic_agent import BasicAgent
except ImportError:  # standalone: no brainstem required
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


# Provider-prefixed tokens, private keys, and explicit credential assignments
# with a real-looking value. A bare word like "api_key" in prose is deliberately
# NOT a match -- a gate that cries wolf on documentation gets switched off.
SECRET_PATTERNS = re.compile(
    r"(ghp|ghu|ghs|gho)_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{40,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|(AZURE_OPENAI_API_KEY|client_secret|secret_key|access_token|api_key)"
    r"""[ \t]*[:=][ \t]*["']?[A-Za-z0-9/+_.-]{20,}""")

# Whole artefact classes that must never ship, regardless of contents. Value
# scanning does not catch a captured session: a work identity, tenant GUIDs and
# key material are not shaped like tokens. You cannot pattern-match the
# identifiers you did not know to look for, but you can refuse the file class.
FORBIDDEN_NAMES = re.compile(
    r"(^|/)("
    r"\.env(\.[\w-]+)?"
    r"|[\w.-]*\.copilot_token"
    r"|[\w.-]*\.pem"
    r"|[\w.-]*_token"
    r"|secrets?\.(json|ya?ml|txt)"
    r"|snapshot-\d{10,}\.html"
    r"|[\w.-]*\.har"
    r")$", re.I)
ALLOW_NAMES = re.compile(
    r"\.(env|settings)\.(example|sample|template)|\.example\.json$", re.I)

SKIP_DIRS = (".git/", "node_modules/", "__pycache__/", "/dist/", "/.venv/")


def _load_denylist():
    """(terms, source, error). Injected only -- never embedded in this file."""
    raw = os.environ.get("RAPP_DENYLIST_TERMS", "")
    if raw.strip():
        return ([t.strip() for t in raw.split(",") if t.strip()],
                "$RAPP_DENYLIST_TERMS", None)
    path = os.environ.get("RAPP_DENYLIST", "")
    if path and os.path.isfile(path):
        try:
            d = json.load(open(path))
        except Exception as e:
            return ([], path, f"unreadable: {e}")
        terms = []
        for e in d.get("entries", d if isinstance(d, list) else []):
            t = e.get("term") if isinstance(e, dict) else e
            rx = e.get("regex") if isinstance(e, dict) else None
            if t:
                terms.append(rx or t)
        return (terms, path, None)
    return ([], None, "not configured")


def _compile(terms, word_boundary):
    out = []
    for t in terms:
        anchored = t in word_boundary or (t.isupper() and len(t) <= 4)
        # A term may already be a regex (separator variants); only escape it if
        # it looks literal, so "bc[-_. ]?hydro" keeps working.
        body = t if re.search(r"[\[\](){}|+*?\\]", t) else re.escape(t)
        out.append((t, re.compile((r"\b" + body + r"\b") if anchored else body,
                                  re.I)))
    return out


class ControlTowerAgent(BasicAgent):
    def __init__(self):
        self.name = "ControlTower"
        self.metadata = {
            "name": self.name,
            "description": (
                "Publishing gate and estate view for an agent estate. Scans a "
                "directory for secrets, forbidden artefact classes (.env, "
                "captured sessions, key files) and injected denylisted names "
                "BEFORE it ships; or reports how many capabilities each agent "
                "runtime on this machine holds. Reports file and count, never "
                "the matched value."),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["gate", "neighborhoods", "denylist"],
                        "description": (
                            "gate: scan a path before publishing. "
                            "neighborhoods: count capabilities per runtime. "
                            "denylist: show roster configuration, not contents."),
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to scan. Required for action=gate.",
                    },
                    "max_findings": {
                        "type": "integer",
                        "description": "Cap findings returned. Default 50.",
                    },
                },
                "required": ["action"],
            },
        }
        super().__init__(name=self.name, metadata=self.metadata)

    # -- actions ----------------------------------------------------------
    def _gate(self, path, cap):
        if not path or not os.path.isdir(path):
            return {"status": "error",
                    "message": f"path is required and must be a directory: {path!r}"}
        terms, source, err = _load_denylist()
        if err:
            # Fail closed. See the module docstring: a gate that passes because
            # it has nothing to check is trusted precisely when it is blind.
            return {
                "status": "refused",
                "reason": f"denylist {err}",
                "fix": ("set $RAPP_DENYLIST to a JSON file with an `entries` "
                        "list, or $RAPP_DENYLIST_TERMS to a comma-separated "
                        "list. Refusing to report CLEAN with nothing to check."),
            }
        wb = set()
        p = os.environ.get("RAPP_DENYLIST", "")
        if p and os.path.isfile(p):
            try:
                wb = set(json.load(open(p)).get("word_boundary_terms", []))
            except Exception:
                pass
        rules = _compile(terms, wb)

        findings, scanned = [], 0
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in
                       (".git", "node_modules", "__pycache__", ".venv", "dist")]
            for fn in files:
                fp = os.path.join(root, fn)
                rel = os.path.relpath(fp, path)
                if any(s in "/" + rel.replace(os.sep, "/") for s in SKIP_DIRS):
                    continue
                if FORBIDDEN_NAMES.search(rel) and not ALLOW_NAMES.search(rel):
                    findings.append({"kind": "forbidden-artefact", "file": rel})
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                        text = fh.read()
                except Exception:
                    continue
                scanned += 1
                n = len(SECRET_PATTERNS.findall(text))
                if n:
                    findings.append({"kind": "secret-pattern", "file": rel,
                                     "matches": n})
                for term, rx in rules:
                    c = len(rx.findall(text))
                    if c:
                        findings.append({"kind": "denylisted-name", "file": rel,
                                         "term": term, "matches": c})
                if len(findings) >= cap:
                    break
        clean = not findings
        return {
            "status": "ok",
            "verdict": "CLEAN" if clean else "NO-GO",
            "safe_to_publish": clean,
            "files_scanned": scanned,
            "roster_source": source,
            "roster_terms": len(terms),
            "findings": findings[:cap],
            "note": ("Values are never reported, only file and count — a leak "
                     "report that quotes the secret is a second copy of it."),
        }

    def _neighborhoods(self):
        home = os.path.expanduser("~")
        hosts = [
            ("RAPP brainstem", os.path.join(home, ".brainstem"),
             [("src/rapp_brainstem/agents", "_agent.py")]),
            ("openrappter", os.path.join(home, ".openrappter"),
             [("brainstem/agents", "_agent.py"), ("typescript/skills", "SKILL.md")]),
            ("openclaw", os.path.join(home, ".openclaw"),
             [("agents", "SKILL.md")]),
            ("claude code", os.path.join(home, ".claude"),
             [("skills", "SKILL.md")]),
        ]
        out, total = [], 0
        for label, root, globs in hosts:
            if not os.path.isdir(root):
                out.append({"host": label, "present": False, "capabilities": 0})
                continue
            n = 0
            for sub, suffix in globs:
                base = os.path.join(root, sub)
                for r, _d, fs in os.walk(base) if os.path.isdir(base) else []:
                    if "node_modules" in r:
                        continue
                    n += sum(1 for f in fs if f.endswith(suffix))
            total += n
            out.append({"host": label, "present": True, "capabilities": n})
        return {"status": "ok", "hosts": out, "total_capabilities": total,
                "note": ("A host holding 0 may keep agents as runtime state "
                         "rather than portable files — that is a property of "
                         "the host, not a missing count.")}

    def _denylist(self):
        terms, source, err = _load_denylist()
        return {"status": "ok", "configured": err is None,
                "source": source, "term_count": len(terms),
                "error": err,
                "note": "Contents are never returned — only how it is wired."}

    def perform(self, **kwargs):
        action = kwargs.get("action")
        cap = int(kwargs.get("max_findings") or 50)
        if action == "gate":
            r = self._gate(kwargs.get("path"), cap)
        elif action == "neighborhoods":
            r = self._neighborhoods()
        elif action == "denylist":
            r = self._denylist()
        else:
            r = {"status": "error",
                 "message": f"unknown action {action!r}",
                 "valid": ["gate", "neighborhoods", "denylist"]}
        return json.dumps(r, indent=2)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--tool":
        print(json.dumps(ControlTowerAgent().to_tool(), indent=2))
    else:
        raw = a[0] if a else (sys.stdin.read().strip() or '{"action":"neighborhoods"}')
        print(ControlTowerAgent().perform(**json.loads(raw)))
