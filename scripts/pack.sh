#!/usr/bin/env bash
# Build distributable .skill packages (zip with <name>/SKILL.md at the root).
#
#   ./scripts/pack.sh [out_dir]
#
# Default out_dir: ./dist
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"

mkdir -p "$OUT"
rm -f "$OUT"/*.skill "$OUT"/SHA256SUMS

shopt -s nullglob
for dir in "$ROOT"/skills/*/; do
  name="$(basename "$dir")"
  stage="$(mktemp -d)"
  mkdir -p "$stage/$name"
  # copy without local junk
  rsync -a \
    --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    "$dir" "$stage/$name/"

  ( cd "$stage" && zip -qr -X "$OUT/$name.skill" "$name" )
  rm -rf "$stage"
  printf '%-28s %6s\n' "$name.skill" "$(du -h "$OUT/$name.skill" | cut -f1)"
done

( cd "$OUT" && shasum -a 256 ./*.skill > SHA256SUMS )
echo
echo "packages: $OUT"
cat "$OUT/SHA256SUMS"
