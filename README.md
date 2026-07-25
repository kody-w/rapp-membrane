# rapp-membrane

**Get value out of a private repo without thinking about what's in it.**

A cell membrane doesn't decide molecule by molecule. Its structure decides what
crosses. This is that, for repositories: you do **not** curate what goes in —
you take the private thing in whatever shape it's already in, and let the
*process* decide what's allowed out the far side.

```bash
membrane.sh rapp ~/my-private-repo my-thing
```

One verb. You do not need to know what an agent is, what an egg is, what
toasting does, or what a denylist is for. You have a thing you want to use as a
rapplication. That is the entire required understanding.

## The hero use case

This pattern exists because of a real need, not a design exercise.

There was a **private control-tower repo** — situational displays, content
gates, flight rules — that was worth sharing, and could not be shared. It was
full of an estate map, a customer roster, decision logs, and the operator's own
name in a hundred places. The obvious approach is to hand-pick the safe files.

That approach is wrong, and it fails in a specific way: **you end up guessing
about files you have not opened.** A careful human pass over that repo declared
it clean. The process then found operator identity in it three more times.

So instead: pack the whole thing as-is, hatch it back out, and let the
*process* decide what is allowed through. What came out the far side was a
publishable rapplication. What it caught on the way is in the record below.

Anything with that shape works the same way — a repo, an internal tool, a SaaS
product you want to mirror into something you control. You are not converting
it. You are membraning it, and the pipeline works out what it becomes.

## The pipeline

| | | |
|---|---|---|
| 1 | **EGG** | Pack the private repo **as-is**. No judgment, no cherry-picking. Curating here is how things get missed — you'd be guessing about files you haven't opened. |
| 2 | **CUBBY** | Push the egg to a **private** cubby. Staging is private on purpose: if the process has a hole, it leaks somewhere that doesn't matter yet. |
| 3 | **HATCH** | Pull it back **out** of the cubbied egg, locally. Inspect what *shipped*, not what you built — and an egg is opaque base64 to every scanner, so nothing can be checked while packed. |
| 4 | **SCAN** | *Now* look for PII, in the hatched tree, where it's visible and enumerable. **This is the checkpoint.** |
| 5 | **PUBLISH** | Only after the scan comes back clean. |

## Shaping is judgment. Screening is machinery.

The membrane is deliberately **not** deterministic end to end, and the split is
the whole design:

| | Who does it | Why |
|---|---|---|
| egg · hatch · digest · **scan** | **machinery** | Pattern matching. Being mechanical is the *point* — a gate that reasons can be argued with. |
| **shape** — what does this become? | **an agent** | Cannot be a case statement over file extensions. That only handles inputs its author imagined, and calls everything else "unshapeable" — which is a fact about the author, not the input. |
| **parity** — does the port still work? | **machinery** | Falsifiable. Doesn't care who wrote the port or how many tries it took. |

So: **judgment produces, determinism verifies.** A bad shaping decision yields a
rejected artifact, never a bad publish — because the gates never ask the shaper
anything.

### Porting, not classifying

Shaping doesn't label a repo. It **reads the code and writes a RAPP version that
does what the original did**, then proves it:

```
ORIGINAL   lines=2 words=9 chars=41 / the: 3 / quick: 1
PORT       lines=2 words=9 chars=41 / the: 3 / quick: 1
           case 1: PARITY   case 2: PARITY   case 3: PARITY
```

`parity.py` compares **facts, not bytes** — a port that prints the same numbers
in a different layout is a correct port. Demanding byte-identical stdout would
reject good work and teach the shaper to imitate formatting instead of
behaviour. It fails a deliberately broken port, which is the only way to know
it's testing anything.

### One thing that did NOT work, recorded so nobody repeats it

The shaping was first delegated to a small context-free model over an API. It
returned prose *asking to be shown the file*, which then got written into a
`.py` and failed to parse — so it looked like the model was getting worse when
it was never returning code at all.

The lesson isn't "models can't port code". It's that **the thing doing the
shaping must be the thing holding the context.** An agent that has actually read
the source can port it. One handed a file listing cannot.

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
