#!/usr/bin/env bash
# Copies the payload v5 contract (schema and golden cases) from the SemanticHub
# repository into tests/contract/payload-v5. SemanticHub owns the contract; the
# copy lets the package tests run without the sender.
#
#   bash scripts/sync-from-semantichub.sh           # copy
#   bash scripts/sync-from-semantichub.sh --check   # compare only
#
# SemanticHub checkout: SH_V2_DIR (default ../../semantichub-v2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SH_V2_DIR="${SH_V2_DIR:-$ROOT/../../semantichub-v2}"
[ -d "$SH_V2_DIR/backend/contracts/payload-v5" ] \
	|| { echo "SemanticHub checkout not found in $SH_V2_DIR. Set SH_V2_DIR." >&2; exit 1; }
SH_V2_DIR="$(cd "$SH_V2_DIR" && pwd)"

SRC="$SH_V2_DIR/backend/contracts/payload-v5"
DST="$ROOT/tests/contract/payload-v5"

if [ "${1:-}" = "--check" ]; then
	if ! diff -r "$SRC" "$DST" >/dev/null 2>&1; then
		diff -r "$SRC" "$DST" | head -n 40 >&2 || true
		echo "ERROR: tests/contract/payload-v5 differs from $SRC." >&2
		echo "Run: bash scripts/sync-from-semantichub.sh" >&2
		exit 1
	fi
	echo "payload v5 contract matches $SH_V2_DIR"
	exit 0
fi

rm -rf "$DST"
mkdir -p "$DST"
cp -R "$SRC/." "$DST/"
echo "copied $(find "$DST" -name '*.json' | wc -l) contract files to $DST"
