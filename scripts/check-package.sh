#!/usr/bin/env bash
# Builds the sdist and wheel and checks what CI checks before a release: the
# package metadata passes twine, the wheel carries no tests, and with
# --tag vX.Y.Z the tag matches semantichub_wagtail.__version__.
#
#   bash scripts/check-package.sh [--tag vX.Y.Z]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=''
while [ $# -gt 0 ]; do
	case "$1" in
		--tag) TAG="$2"; shift 2 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/semantichub_wagtail/__init__.py")"
[ -n "$VERSION" ] || { echo "ERROR: no __version__ in semantichub_wagtail/__init__.py" >&2; exit 1; }
grep -q "^## \[$VERSION\]" "$ROOT/CHANGELOG.md" \
	|| { echo "ERROR: CHANGELOG.md has no entry for $VERSION" >&2; exit 1; }
if [ -n "$TAG" ] && [ "$TAG" != "v$VERSION" ]; then
	echo "ERROR: tag $TAG does not match version $VERSION" >&2
	exit 1
fi

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
python -m build --outdir "$OUT" "$ROOT" >/dev/null
python -m twine check --strict "$OUT"/*
WHEEL="$(ls "$OUT"/*.whl)"
if python -m zipfile -l "$WHEEL" | grep -qE '(^|/)tests/'; then
	echo "ERROR: wheel ships tests" >&2
	exit 1
fi
echo "package $VERSION OK"
