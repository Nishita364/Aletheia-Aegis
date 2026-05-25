#!/usr/bin/env bash
# Build script for the browser extension.
# Usage:
#   ./build.sh            — uses manifest.json (MV3, Chrome 114+)
#   ./build.sh --firefox  — uses manifest.v2.json (MV2, Firefox 115+)

set -euo pipefail

FIREFOX=false

for arg in "$@"; do
  case "$arg" in
    --firefox)
      FIREFOX=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--firefox]" >&2
      exit 1
      ;;
  esac
done

if [ "$FIREFOX" = true ]; then
  TARGET="firefox"
  DIST_DIR="dist/firefox"
else
  TARGET="chrome"
  DIST_DIR="dist/chrome"
fi

mkdir -p "${DIST_DIR}"

# Copy common files
cp background.js content.js popup.html popup.js "${DIST_DIR}/"
cp -r icons "${DIST_DIR}/"

if [ "$FIREFOX" = true ]; then
  cp manifest.v2.json "${DIST_DIR}/manifest.json"
  echo "Built Firefox (MV2) extension → ${DIST_DIR}/"
else
  cp manifest.json "${DIST_DIR}/manifest.json"
  echo "Built Chrome (MV3) extension → ${DIST_DIR}/"
fi
