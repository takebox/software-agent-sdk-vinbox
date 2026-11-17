#!/usr/bin/env bash
# Build the five Vinbox distributions into dist-vinbox/.
#
#   handprint-vinbox-sdk
#   handprint-vinbox-tools
#   handprint-vinbox-workspace
#   handprint-vinbox-agent-server
#   software-agent-sdk-vinbox      (meta package, installs the four above)
#
# Nothing is uploaded here. Uploading is a separate, explicit step; see
# PUBLISH-VINBOX.md. The token never lives in this repository.
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="dist-vinbox"
rm -rf "$OUT"
mkdir -p "$OUT"

python -m pip install --upgrade --quiet build

for pkg in \
  vinbox-sdk \
  vinbox-tools \
  vinbox-workspace \
  vinbox-agent-server \
  vinbox-package
do
  echo "== building $pkg"
  python -m build --wheel --outdir "$OUT" "$pkg"
done

echo
echo "== wheels"
ls -l "$OUT"
echo
echo "Next: PUBLISH-VINBOX.md (twine upload, token via environment)."
