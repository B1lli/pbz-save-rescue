#!/usr/bin/env bash
# Install the Oodle decoder used to read PBZ saves.
# Fetches the prebuilt oozextract 0.5.7 WASM (MIT) that SaveSmith ships, and verifies
# its SHA-256 before installing to ~/.cache/pbz-save-rescue/oozextract.
# This downloads third-party code: ask the user before running it.
set -euo pipefail
DEST="${PBZ_OOZ_DIR:-$HOME/.cache/pbz-save-rescue/oozextract}"
WASM_SHA256="a4207524a1edee6a67bd8fb3707011adb32a244595149d3ddf86fddedbc32a94"
SRC_PATH="src/games/phantom-blade-zero/codec/oodle/oozextract"

command -v node >/dev/null || { echo "node is required" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet --depth 1 --filter=blob:none --sparse https://github.com/gundamff/SaveSmith "$TMP/SaveSmith"
git -C "$TMP/SaveSmith" sparse-checkout set "$SRC_PATH" >/dev/null
GOT="$(sha256sum "$TMP/SaveSmith/$SRC_PATH/oozextract_bg.wasm" | cut -d' ' -f1)"
if [ "$GOT" != "$WASM_SHA256" ]; then
  echo "SHA-256 mismatch for oozextract_bg.wasm (got $GOT); not installing" >&2
  exit 1
fi
mkdir -p "$DEST"
cp "$TMP/SaveSmith/$SRC_PATH/oozextract.js" "$TMP/SaveSmith/$SRC_PATH/oozextract_bg.wasm" "$DEST/"
echo "installed Oodle decoder to $DEST"
