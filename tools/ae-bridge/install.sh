#!/bin/bash
# Installs the Claude Bridge panel into After Effects (CEP extensions folder).
# After installing, restart AE and open Window > Extensions > Claude Bridge.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/extension"
DST="$HOME/Library/Application Support/Adobe/CEP/extensions/com.claude.ae-bridge"
for v in 10 11 12 13; do defaults write "com.adobe.CSXS.$v" PlayerDebugMode 1; done   # unsigned panels
rm -rf "$DST"
mkdir -p "$DST"
cp -R "$SRC"/ "$DST"/
echo "installed to $DST"
