#!/usr/bin/env bash
# Explicit optional host installation. Claude installation never runs this.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${HOME}/.local"
if [ "${1:-}" = --prefix ] && [ "$#" -eq 2 ]; then
  PREFIX="$2"
elif [ "$#" -gt 0 ]; then
  echo 'Usage: install-hosts.sh [--prefix /absolute/path]' >&2
  exit 2
fi
[[ "$PREFIX" = /* ]] || { echo 'The installation prefix must be absolute.' >&2; exit 2; }
for tool in node npm curl jq tar; do
  command -v "$tool" >/dev/null || { echo "Missing host-install prerequisite: $tool" >&2; exit 1; }
done
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 19) ? 0 : 1)' || { echo 'Pi requires Node 22.19 or newer.' >&2; exit 1; }
PI_VERSION=$(jq -er '.pi' "$ROOT/hosts/versions.json")
AUTOLITH_VERSION=$(jq -er '.autolith' "$ROOT/hosts/versions.json")
case "$(uname -s):$(uname -m)" in
  Linux:x86_64) PLATFORM=x86_64-linux ;;
  Linux:aarch64) PLATFORM=aarch64-linux ;;
  Darwin:arm64) PLATFORM=arm64-darwin ;;
  Darwin:x86_64) PLATFORM=x86_64-darwin ;;
  *) echo 'No pinned Autolith release for this platform. Install it from the official release page.' >&2; exit 1 ;;
esac
EXPECTED_SHA=$(jq -er --arg platform "$PLATFORM" '.autolith_sha256[$platform]' "$ROOT/hosts/versions.json")
DESTINATION="$PREFIX/share/autolith/releases/$AUTOLITH_VERSION"
LINK="$PREFIX/bin/autolith"
if { [ -e "$LINK" ] || [ -L "$LINK" ]; } && ! [[ -L "$LINK" && "$(readlink "$LINK")" = "$PREFIX/share/autolith/releases/"* ]]; then
  echo "Preserving existing unmanaged Autolith executable: $LINK" >&2
  exit 1
fi
npm install --global --ignore-scripts --prefix "$PREFIX" "@earendil-works/pi-coding-agent@$PI_VERSION"
if [ ! -f "$DESTINATION/RELEASE" ] || ! INSTALLED_VERSION=$(sed -n 's/^version=//p' "$DESTINATION/RELEASE") || [ "$INSTALLED_VERSION" != "$AUTOLITH_VERSION" ]; then
  SCRATCH=$(mktemp -d)
  trap 'rm -rf "$SCRATCH"' EXIT
  ARCHIVE="autolith-v$AUTOLITH_VERSION-$PLATFORM.tar.gz"
  curl --fail --location --retry 3 "https://github.com/lambda-symbolics/autolith/releases/download/v$AUTOLITH_VERSION/$ARCHIVE" --output "$SCRATCH/$ARCHIVE"
  if command -v sha256sum >/dev/null; then
    ACTUAL_SHA=$(sha256sum "$SCRATCH/$ARCHIVE")
  else
    ACTUAL_SHA=$(shasum -a 256 "$SCRATCH/$ARCHIVE")
  fi
  [ "${ACTUAL_SHA%% *}" = "$EXPECTED_SHA" ] || { echo 'Autolith checksum mismatch.' >&2; exit 1; }
  mkdir -p "$DESTINATION"
  tar -xzf "$SCRATCH/$ARCHIVE" --strip-components=1 -C "$DESTINATION"
fi
mkdir -p "$PREFIX/bin"
ln -sfn "$DESTINATION/bin/autolith" "$LINK"
printf 'Installed Pi %s and Autolith %s. Add %s/bin to PATH.\n' "$PI_VERSION" "$AUTOLITH_VERSION" "$PREFIX"
