# rapp-membrane

**Get value out of a private repo without thinking about what's in it.**

A cell membrane doesn't decide molecule by molecule. Its structure decides what
crosses. This is that, for repositories: you do **not** curate what goes in —
you take the private thing in whatever shape it's already in, and let the
*process* decide what's allowed out the far side.

```bash
membrane.sh pull ~/my-private-repo my-thing
```

## The pull

| | | |
|---|---|---|
| 1 | **EGG** | Pack the private repo **as-is**. No judgment, no cherry-picking. Curating here is how things get missed — you'd be guessing about files you haven't opened. |
| 2 | **CUBBY** | Push the egg to a **private** cubby. Staging is private on purpose: if the process has a hole, it leaks somewhere that doesn't matter yet. |
| 3 | **HATCH** | Pull it back **out** of the cubbied egg, locally. Inspect what *shipped*, not what you built — and an egg is opaque base64 to every scanner, so nothing can be checked while packed. |
| 4 | **SCAN** | *Now* look for PII, in the hatched tree, where it's visible and enumerable. **This is the checkpoint.** |
| 5 | **PUBLISH** | Only after the scan comes back clean. |

## This is a workflow, not a scrubber

Nothing here is magic and nothing is fully deterministic. The value is that
inspection happens at the one place where inspection is actually possible —
after the artifact exists, in the shape it will exist in.

Findings are **reported, never silently rewritten**. You decide each one:
redact it, drop the file, or accept it deliberately. Auto-rewriting is how a
process starts lying about what it shipped.

## What it checks

- **Universal identifiers** — email addresses, home paths. Always, no config.
- **The operator** — `$MEMBRANE_OPERATOR`. *A roster covers other people. It
  does not cover you*, and a private tree is full of your own name and handle.
  Matched case-insensitively, because `jdoe_record_agent.py` is the same person
  as `JDoe`.
- **Your roster** — `$RAPP_DENYLIST` (json) or `$RAPP_DENYLIST_TERMS`. Injected,
  never committed: a stored list of names you must never publish **is** the
  disclosure it exists to prevent.
- **Secrets and artefact classes** — provider tokens, private keys, `.env`,
  captured sessions, `.har`. Shape-based as well as value-based, because a
  captured session's identifiers aren't shaped like tokens: you can't
  pattern-match what you didn't know to look for, but you *can* refuse the file
  class that carries it.

## It found things a careful human pass missed

Run against a real private control-tower repo:

- First pass **blocked** with **107 findings** — operator name in 25 files, plus
  denylisted names in `dashboard.html`, `FLIGHT_RULES.md`, `RECOVERY.md`.
- After remediation, a hand-verified "clean" tree still tripped it: one operator
  reference survived, then two more — a lowercase handle and a filename
  containing it — that case-sensitive checks had walked straight past.

That's the point. The tree had already been declared clean by inspection. The
process disagreed, and the process was right.

## Refusals are the feature

- Unconfigured roster → **refuse**, never "clean". A gate that passes with
  nothing to check reports CLEAN exactly when it's blind.
- Digest mismatch on hatch → **refuse**.
- Findings present → **publish blocked**, non-zero exit.

## Files

- `membrane.sh` — the pull
- `control_tower_agent.py` — the scan, as a single-file agent. Runs standalone
  (`python3 control_tower_agent.py --tool`) or drops into a RAPP brainstem.

Apache-2.0.
