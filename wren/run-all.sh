#!/usr/bin/env bash
# Queue every Wren test, back to back, unattended. Run from WSL:
#
#   bash wren/run-all.sh https://<your-tunnel>.trycloudflare.com
#
# W1, W2, W5 and W7 change shared settings (budget, Use recommended model, Routing level), so each
# gets its own run; the other six share one final run. Runs go one after another (--wait), never
# at the same time. seldon.yml itself is not changed: each run uses a copy in wren/.runs/, which
# is deleted at the end. Reports land in wren/reports/<time>/.
#
# DRY=1 bash wren/run-all.sh <url>   shows what each run would include, without running anything.
set -u

URL="${1:?usage: bash wren/run-all.sh <tunnel url>}"
cd "$(dirname "$0")/.."

SOLO=(w1-overkill w2-budget w5-real-work w7-routing)
stamp=$(date +%Y%m%d-%H%M%S)
reports="wren/reports/$stamp"
work="wren/.runs"
mkdir -p "$reports" "$work"
trap 'rm -rf "$work"' EXIT

# A copy of seldon.yml with Unix line endings and no `only:` flags.
base() { sed 's/\r$//' seldon.yml | sed '/^    only: true$/d'; }

make_solo() {   # $1 = case id
  mkdir -p "$work/$1"
  base | sed "s/^    id: $1\$/&\n    only: true/" > "$work/$1/seldon.yml"
}

make_rest() {
  mkdir -p "$work/rest"
  local f="$work/rest/seldon.yml"
  base > "$f"
  for id in "${SOLO[@]}"; do sed -i "s/^    id: $id\$/&\n    skip: true/" "$f"; done
}

run_one() {     # $1 = group name
  local f="$work/$1/seldon.yml"
  if [ "${DRY:-}" = 1 ]; then
    echo "== $1 would run:"
    awk '/^    id:/{id=$2} /^    only: true/{only[id]=1} /^    skip: true/{skip[id]=1}
         /^    id:/{ids[++n]=$2}
         END{any=0; for(i=1;i<=n;i++) if(only[ids[i]]) any=1;
             for(i=1;i<=n;i++){ x=ids[i]; if((any && only[x]) || (!any && !skip[x])) printf "   %s\n", x }}' "$f"
    return 0
  fi
  echo "== $(date +%H:%M:%S) starting $1"
  if ! seldon validate --file "$f" >/dev/null; then
    echo "   $1: seldon.yml copy is not valid, skipped" | tee "$reports/$1.md"
    return 1
  fi
  seldon run --wait --md --url "$URL" --file "$f" > "$reports/$1.md" 2>&1
  echo "   $1 done: $(grep -m1 -oE '[0-9]+/[0-9]+ (test cases )?passed[^.]*' "$reports/$1.md" || echo 'see report')"
}

for id in "${SOLO[@]}"; do make_solo "$id"; done
make_rest

for group in "${SOLO[@]}" rest; do run_one "$group"; done

[ "${DRY:-}" = 1 ] && exit 0
echo
echo "All runs finished. Reports: $reports/"
ls -1 "$reports"
