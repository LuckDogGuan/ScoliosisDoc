#!/bin/bash
# Wrap a verified immutable release; never rebuild/overwrite the release itself.
set -euo pipefail
cd "$(dirname "$0")/.."
label=${1:-v3.3.0-20261002-results}
case "$label" in ''|.*|*[!A-Za-z0-9._-]*) echo 'Invalid release label' >&2; exit 2;; esac
release=image/$label
[ -d "$release" ] || { echo "Missing release: $release" >&2; exit 2; }
(cd "$release"; sha256sum -c SHA256SUMS)
bundle_label=${2:-$label-bundle1}
case "$bundle_label" in ''|.*|*[!A-Za-z0-9._-]*) echo 'Invalid bundle label' >&2; exit 2;; esac
output=bundles/$bundle_label
[ ! -e "$output" ] || { echo "Bundle already exists: $output" >&2; exit 2; }
name=instrument-$bundle_label
mkdir -p "$output"
cp -a "$release" "$output/$name"
cp deploy/install_bundle.sh deploy/button_inputs.sh deploy/S79buttons deploy/wpa_supplicant.default.conf "$output/$name/deploy/"
cp "$release/SHA256SUMS" "$output/$name/SOURCE_SHA256SUMS"
printf 'bundle_source_release=%s\nbundle_tool_commit=%s\nbundle_created_utc=%s\n' "$label" "$(git rev-parse HEAD)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$output/$name/BUNDLE.txt"
(cd "$output/$name"; find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort | xargs sha256sum >SHA256SUMS; sh deploy/install_bundle.sh --check)
tar --sort=name -cf - -C "$output" "$name" | gzip -n >"$output/$name.tar.gz"
(cd "$output"; sha256sum "$name.tar.gz" >SHA256SUMS)
printf 'Bundle: %s/%s.tar.gz\n' "$output" "$name"