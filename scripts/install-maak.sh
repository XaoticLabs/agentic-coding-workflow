#!/usr/bin/env bash
# Install the checksum-verified Maak release used by local development and CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${HOME}/.local"
if [ "${1:-}" = --prefix ] && [ "$#" -eq 2 ]; then
  PREFIX="$2"
elif [ "$#" -gt 0 ]; then
  echo 'Usage: install-maak.sh [--prefix /absolute/path]' >&2
  exit 2
fi
[[ "$PREFIX" = /* ]] || { echo 'The installation prefix must be absolute.' >&2; exit 2; }
for tool in bash guile curl jq tar getopt; do
  command -v "$tool" >/dev/null || { echo "Missing Maak prerequisite: $tool (see README.md)" >&2; exit 1; }
done
guile -c '(unless (string-prefix? "3.0" (effective-version)) (exit 1))' || {
  echo 'Maak requires Guile 3.0.' >&2; exit 1;
}
# The upstream launcher uses GNU getopt, including on macOS.
if getopt --test >/dev/null 2>&1; then
  echo 'Maak requires GNU getopt (see README.md).' >&2; exit 1
else
  [ "$?" -eq 4 ] || { echo 'Maak requires GNU getopt (see README.md).' >&2; exit 1; }
fi
VERSION=$(jq -er '.version' "$ROOT/scripts/maak.lock.json")
COMMIT=$(jq -er '.commit' "$ROOT/scripts/maak.lock.json")
EXPECTED_SHA=$(jq -er '.sha256' "$ROOT/scripts/maak.lock.json")
DESTINATION="$PREFIX/share/maak/$COMMIT"
LAUNCHER="$PREFIX/bin/maak"
MARKER='# Managed by agentic-coding-workflow scripts/install-maak.sh.'
if { [ -e "$LAUNCHER" ] || [ -L "$LAUNCHER" ]; } && ! grep -Fqx "$MARKER" "$LAUNCHER"; then
  echo "Preserving existing unmanaged Maak executable: $LAUNCHER" >&2
  exit 1
fi
SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
if [ -e "$DESTINATION" ]; then
  [ -x "$DESTINATION/scripts/maak" ] || { echo "Incomplete Maak installation: $DESTINATION" >&2; exit 1; }
else
  curl --fail --location --retry 3 --connect-timeout 15 --max-time 120 \
    "https://codeberg.org/jjba23/maak/archive/$COMMIT.tar.gz" --output "$SCRATCH/maak.tar.gz"
  if command -v sha256sum >/dev/null; then
    ACTUAL_SHA=$(sha256sum "$SCRATCH/maak.tar.gz")
  else
    ACTUAL_SHA=$(shasum -a 256 "$SCRATCH/maak.tar.gz")
  fi
  [ "${ACTUAL_SHA%% *}" = "$EXPECTED_SHA" ] || { echo 'Maak checksum mismatch.' >&2; exit 1; }
  mkdir -p "$SCRATCH/source" "$PREFIX/share/maak"
  tar -xzf "$SCRATCH/maak.tar.gz" --strip-components=1 -C "$SCRATCH/source"
  chmod +x "$SCRATCH/source/scripts/maak"
  mv "$SCRATCH/source" "$DESTINATION"
fi
# Invoke the upstream launcher at its real path so it finds its own modules.
mkdir -p "$PREFIX/bin"
# Interpreting these small tasks avoids implicit writes to Guile's user cache
# in repository sandboxes. Developers can explicitly enable compilation.
# shellcheck disable=SC2016 # Expand these variables when the installed launcher runs.
printf '#!/usr/bin/env bash\n%s\nexport GUILE_AUTO_COMPILE="${GUILE_AUTO_COMPILE:-0}"\nexec bash %q "$@"\n' \
  "$MARKER" "$DESTINATION/scripts/maak" > "$SCRATCH/maak"
chmod +x "$SCRATCH/maak"
mv "$SCRATCH/maak" "$LAUNCHER"
GUILE_AUTO_COMPILE=0 "$LAUNCHER" --version
printf 'Installed Maak %s. Add %s/bin to PATH.\n' "$VERSION" "$PREFIX"
