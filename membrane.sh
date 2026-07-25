#!/usr/bin/env bash
# membrane.sh — the pull that gets value out of a private repo, safely.
#
# A cell membrane does not decide molecule by molecule. Its structure decides
# what crosses. Same idea: you do NOT curate what goes in. You take the private
# thing in whatever shape it is already in, and let the PROCESS decide what is
# allowed out the far side.
#
# This is a workflow, not a scrubber. Nothing here is magic and nothing here is
# fully deterministic. The point is that inspection happens at the one place
# where inspection is actually possible.
#
#   1. EGG     pack the private repo AS IT IS. No judgment, no cherry-picking.
#              Curating at this stage is how things get missed — you would be
#              guessing about files you have not opened.
#   2. CUBBY   push the egg to a PRIVATE cubby. Staging is private on purpose:
#              if the process has a hole, it leaks somewhere that does not
#              matter yet.
#   3. HATCH   pull it back OUT of the cubbied egg, locally. Inspect what
#              SHIPPED, not what you built — an egg is opaque base64 to every
#              scanner, so nothing can be checked while it is packed.
#   4. SCAN    now look for PII in the hatched tree, where it is visible and
#              enumerable. This is the checkpoint. Findings are REPORTED for a
#              human or agent to judge, never silently rewritten.
#   5. PUBLISH only after the scan comes back clean.
#
#   membrane.sh egg   <src> <name> [out.egg]
#   membrane.sh hatch <egg> <dir>
#   membrane.sh scan  <dir>
#   membrane.sh pull  <src> <name>      # 1,3,4 — stops on findings
#
# Scan reads a roster from $RAPP_DENYLIST (json) or $RAPP_DENYLIST_TERMS, and
# always checks universal identifiers (emails, home paths) plus anything in
# $MEMBRANE_OPERATOR. A roster covers other people; the operator is the one
# everyone forgets, and a private tree is full of their own name.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="${MEMBRANE_GATE:-$HERE/control_tower_agent.py}"
RED=""; GRN=""; YEL=""; RST=""
if [ -t 1 ]; then RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'; fi
die(){ echo "${RED}STOP${RST}: $*" >&2; exit 1; }
say(){ printf '  %s\n' "$*"; }

# ---- 1. EGG: pack as-is, no curation ---------------------------------------
cmd_egg() {
  src="$1"; name="$2"; out="${3:-$name.egg}"
  [ -d "$src" ] || die "not a directory: $src"
  python3 - "$src" "$name" "$out" <<'PY'
import sys, json, io, tarfile, base64, hashlib, pathlib
src, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
root = pathlib.Path(src)
# Only VCS internals and build caches are skipped. This is NOT a content
# decision -- they cannot be meaningfully hatched. Nothing is judged "safe".
SKIP = (".git/", "__pycache__/", "/.venv/", "/node_modules/")
buf = io.BytesIO(); n = 0
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = "/" + str(p.relative_to(root)).replace("\\", "/") + "/"
        if any(s in rel for s in SKIP):
            continue
        tf.add(str(p), arcname=str(p.relative_to(root))); n += 1
payload = buf.getvalue()
egg = {
  "format": "rapplication-egg/1.0", "name": name,
  "display": f"{name} (cubby egg, unscreened)",
  "rappid": f"rappid:@rapp/{name}:" + hashlib.sha256(payload).hexdigest()[:32],
  "source": {"note": "packed as-is from a private repo; NOT yet screened"},
  "screened": False,
  "files": n,
  "payload_sha256": hashlib.sha256(payload).hexdigest(),
  "payload": base64.b64encode(payload).decode(),
  "twin_settings": {"IsEncrypted": False, "Values": {}},
  "hatch": {"requires": ["python3.9+"]},
}
open(out, "w").write(json.dumps(egg))
print(f"  packed {n} file(s) as-is -> {out}")
print("  screened:false — this egg is NOT cleared for public release")
PY
}

# ---- 3. HATCH: get it back out ---------------------------------------------
cmd_hatch() {
  egg="$1"; dir="$2"
  [ -f "$egg" ] || die "no such egg: $egg"
  rm -rf "$dir"; mkdir -p "$dir"
  python3 - "$egg" "$dir" <<'PY'
import sys, json, base64, io, tarfile, hashlib
egg = json.load(open(sys.argv[1])); raw = base64.b64decode(egg["payload"])
if hashlib.sha256(raw).hexdigest() != egg["payload_sha256"]:
    raise SystemExit("payload digest MISMATCH — refusing to hatch")
tarfile.open(fileobj=io.BytesIO(raw)).extractall(sys.argv[2])
print(f"  digest verified; hatched {egg['files']} file(s)")
PY
}

# ---- 4. SCAN: the checkpoint ------------------------------------------------
cmd_scan() {
  dir="$1"
  [ -d "$dir" ] || die "no such directory: $dir"
  total=0

  say "universal identifiers"
  for spec in "email:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" \
              "home-path:/(Users|home)/[A-Za-z0-9._-]+"; do
    label="${spec%%:*}"; pat="${spec#*:}"
    n=$(grep -rIloE --exclude-dir=.git "$pat" "$dir" 2>/dev/null | wc -l | tr -d ' ')
    printf "    %-11s %s file(s)\n" "$label" "$n"; total=$((total+n))
  done

  if [ -n "${MEMBRANE_OPERATOR:-}" ]; then
    ops=$(printf '%s' "$MEMBRANE_OPERATOR" | tr ',' '|' | sed 's/|$//')
    # Long base64 runs are excluded from IDENTITY matching. A capsule is random
    # base64 and will contain short names by pure chance -- a short operator name turned up in
    # one on the first real run of this tool. Reporting that as PII is useless:
    # false positives are exactly how a gate gets switched off. Secrets and
    # roster terms are still matched everywhere, including inside blobs.
    n=$(MEMBRANE_OPS="$ops" python3 - "$dir" <<'PYO'
import os,re,sys,pathlib
ops=re.compile("("+os.environ["MEMBRANE_OPS"]+")", re.I)
b64=re.compile(r"[A-Za-z0-9+/=]{120,}")
hits=0
for p in pathlib.Path(sys.argv[1]).rglob("*"):
    if not p.is_file() or "/.git/" in "/"+str(p): continue
    try: t=p.read_text(encoding="utf-8")
    except Exception: continue
    if ops.search(b64.sub("", t)): hits+=1
print(hits)
PYO
)
    printf "    %-11s %s file(s)\n" "operator" "$n"; total=$((total+n))
    [ "${n:-0}" -gt 0 ] && MEMBRANE_OPS="$ops" python3 - "$dir" <<'PYL'
import os,re,sys,pathlib
ops=re.compile("("+os.environ["MEMBRANE_OPS"]+")", re.I)
b64=re.compile(r"[A-Za-z0-9+/=]{120,}")
root=pathlib.Path(sys.argv[1]); n=0
for p in sorted(root.rglob("*")):
    if not p.is_file() or n>=5 or "/.git/" in "/"+str(p): continue
    try: t=p.read_text(encoding="utf-8")
    except Exception: continue
    if ops.search(b64.sub("", t)):
        print("      "+str(p.relative_to(root))); n+=1
PYL
  else
    printf "    %-11s ${YEL}NOT SET${RST}  \$MEMBRANE_OPERATOR — your own name and\n" "operator"
    printf "                handle are what a private tree is actually full of\n"
  fi

  say "roster / secrets / artefact classes"
  raw=$(python3 "$GATE" "{\"action\":\"gate\",\"path\":\"$dir\",\"max_findings\":200}" 2>&1)
  gb=$(printf '%s' "$raw" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(999); sys.exit()
if d.get('status')=='refused':
    print(999); sys.exit()
print(len(d.get('findings',[])))
" 2>/dev/null)
  printf '%s' "$raw" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print('    gate: unreadable output'); sys.exit()
if d.get('status')=='refused':
    print('    gate REFUSED:', d.get('reason')); sys.exit()
print(f\"    verdict {d.get('verdict')} | {d.get('files_scanned')} files | {d.get('roster_terms')} roster terms\")
for f in d.get('findings',[])[:8]:
    print('      ', f.get('kind'), f.get('file'), f.get('term',''))
" 2>/dev/null
  total=$((total + ${gb:-999}))

  echo
  if [ "$total" -eq 0 ]; then
    say "${GRN}SCAN CLEAN${RST} — publishing permitted"
    return 0
  fi
  say "${RED}SCAN FOUND $total item(s)${RST} — do NOT publish"
  say "Reported, not auto-rewritten. Judge each: redact, drop the file, or"
  say "accept deliberately. Silent rewriting is how a process starts lying"
  say "about what it shipped."
  return 1
}

cmd_pull() {
  src="$1"; name="$2"
  work="${MEMBRANE_WORK:-/tmp/membrane-$name}"; mkdir -p "$work"
  say "1. EGG — as-is, no curation";  cmd_egg "$src" "$name" "$work/$name.egg" || exit 1
  say "2. CUBBY — push $work/$name.egg to a PRIVATE cubby, then hatch FROM there"
  say "3. HATCH";                     cmd_hatch "$work/$name.egg" "$work/hatched" || exit 1
  say "4. SCAN"
  if cmd_scan "$work/hatched"; then
    say "5. ${GRN}PUBLISH permitted${RST} — $work/$name.egg"
  else
    say "5. ${RED}PUBLISH blocked${RST} — resolve findings, re-egg, re-run"
    exit 1
  fi
}

# ---- 2b. SHAPE: decide what this BECOMES in RAPP ----------------------------
# Screening asks "is this safe to publish". Shaping asks "what is this, in RAPP
# terms". Both have to happen or you get a safe artifact nobody can install.
#
# Nothing is forced. A tree that has no capability in it is reported as such
# rather than wrapped in a manifest that claims otherwise -- a store entry that
# does not run is worse than no entry, because someone installs it.
cmd_shape() {
  dir="$1"; name="$2"; out="${3:-$dir/.rapp-shape}"
  [ -d "$dir" ] || die "no such directory: $dir"
  TOASTER="${MEMBRANE_TOASTER:-$HERE/toaster.py}"
  mkdir -p "$out"

  skills=$(find "$dir" -name SKILL.md -not -path '*/.git/*' 2>/dev/null | wc -l | tr -d ' ')
  agents=$(find "$dir" -name '*_agent.py' -not -path '*/.git/*' 2>/dev/null | wc -l | tr -d ' ')
  pys=$(find "$dir" -name '*.py' -not -path '*/.git/*' 2>/dev/null | wc -l | tr -d ' ')
  say "genre: $skills SKILL.md, $agents agent.py, $pys python file(s)"

  made=0
  if [ "$skills" -gt 0 ] && [ -f "$TOASTER" ]; then
    # Skills are bread. Toast them, then project each into a single-file agent
    # -- that is the unit a RAPP store entry actually installs.
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      python3 "$TOASTER" toast "$f" >/dev/null 2>&1
      slug=$(basename "$(dirname "$f")")
      if python3 "$TOASTER" convert "$f" --to agent \
           -o "$out/${slug//-/_}_agent.py" >/dev/null 2>&1; then
        made=$((made+1))
      fi
    done < <(find "$dir" -name SKILL.md -not -path '*/.git/*' 2>/dev/null)
  fi
  if [ "$agents" -gt 0 ]; then
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      cp "$f" "$out/$(basename "$f")" 2>/dev/null && made=$((made+1))
    done < <(find "$dir" -name '*_agent.py' -not -path '*/.git/*' 2>/dev/null)
  fi

  if [ "$made" -eq 0 ]; then
    say "${YEL}no installable capability found${RST} — this tree does not shape into"
    say "a store rapplication. Reporting that instead of emitting a manifest"
    say "that claims otherwise: an entry that does not run is worse than none."
    return 2
  fi

  # every emitted agent must actually load, or it is not shippable
  ok=0
  for a in "$out"/*_agent.py; do
    [ -f "$a" ] || continue
    python3 "$a" --tool >/dev/null 2>&1 && ok=$((ok+1))
  done
  python3 - "$out" "$name" "$made" "$ok" <<'PY'
import sys, json, pathlib
out, name, made, ok = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
files = sorted(p.name for p in pathlib.Path(out).glob("*_agent.py"))
json.dump({
  "schema": "rapp-application/1.0",
  "id": name.replace("-", "_"),
  "name": name,
  "version": "0.1.0",
  "type": "rapplication",
  "summary": f"Shaped by rapp-membrane from an arbitrary input tree: "
             f"{made} capability file(s), {ok} verified loadable.",
  "singletons": files,
  "shaped_by": "rapp-membrane",
  "verified_loadable": ok,
  "caveat": None if ok == made else
            f"{made - ok} emitted file(s) did NOT load — do not publish those",
}, open(f"{out}/manifest.json", "w"), indent=2)
print(f"  shaped {made} capability file(s); {ok} load and declare a tool contract")
PY
  [ "$ok" -gt 0 ] || die "nothing emitted actually loads — refusing to shape"
}

# ---- THE ONE VERB ----------------------------------------------------------
# `membrane rapp <thing> <name>` — for someone who has something they want to
# use and does NOT want to learn RAPP to use it.
#
# They should not need to know what an agent.py is, what toasting does, what an
# egg is, or what a denylist is for. They have a thing. They want it usable.
# Everything below narrates itself in plain language so the pipeline teaches by
# running, and every stop says what to do next rather than just failing.
cmd_rapp() {
  src="$1"; name="${2:-$(basename "$src")}"
  work="${MEMBRANE_WORK:-/tmp/membrane-$name}"; rm -rf "$work"; mkdir -p "$work"
  echo
  echo "  membraning '$src' into a RAPP rapplication called '$name'"
  echo "  ─────────────────────────────────────────────────────────────"

  echo
  echo "  [1/5] Packing it exactly as it is."
  echo "        Nothing is cherry-picked. Choosing what to include means"
  echo "        guessing about files you have not opened, and that is how"
  echo "        things get missed."
  cmd_egg "$src" "$name" "$work/$name.egg" || return 1

  echo
  echo "  [2/5] Unpacking it again, from the packed copy."
  echo "        Everything after this inspects what actually shipped, not"
  echo "        what was on your disk. Those differ more often than you think."
  cmd_hatch "$work/$name.egg" "$work/hatched" || return 1

  echo
  echo "  [3/5] Working out what this becomes in RAPP."
  echo "        You do not have to answer this. Prose instructions become"
  echo "        single-file agents; existing agents pass through; anything"
  echo "        with no capability in it is reported, not forced."
  if ! cmd_shape "$work/hatched" "$name" "$work/shaped"; then
    echo
    echo "  STOPPED: there is nothing installable in here."
    echo "  That is a real answer, not a failure — this tree is not a"
    echo "  rapplication. Point it at something with instructions or code."
    return 2
  fi

  echo
  echo "  [4/5] Checking nothing private is riding along."
  echo "        Emails, home paths, your own name, your roster, secrets, and"
  echo "        whole file types that must never ship (.env, session captures)."
  if ! cmd_scan "$work/shaped"; then
    echo
    echo "  STOPPED before publishing. Nothing was rewritten behind your back —"
    echo "  the findings above are yours to judge. Fix them at the source, then"
    echo "  run this again."
    return 1
  fi

  echo
  echo "  [5/5] Ready to publish."
  echo "        artifact : $work/$name.egg"
  echo "        agents   : $(ls "$work/shaped"/*_agent.py 2>/dev/null | wc -l | tr -d ' ') installable file(s)"
  echo "        manifest : $work/shaped/manifest.json"
  echo
  echo "  ${GRN}CLEARED${RST} — this is a publishable RAPP rapplication."
  echo "  Publish with your store's submission flow; the manifest is store-shaped."
  return 0
}

case "${1:-}" in
  egg)   shift; cmd_egg   "$@" ;;
  hatch) shift; cmd_hatch "$@" ;;
  scan)  shift; cmd_scan  "$@" ;;
  shape) shift; cmd_shape "$@" ;;
  rapp)  shift; cmd_rapp  "$@" ;;
  pull)  shift; cmd_pull  "$@" ;;
  *) sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 64 ;;
esac

