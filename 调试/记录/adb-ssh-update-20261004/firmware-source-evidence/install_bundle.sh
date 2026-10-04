#!/bin/sh
# Trusted release bundle only; the expected outer SHA256 must be checked by the operator.
set -eu
cd "$(dirname "$0")/.."
package=$(pwd)
mode=${1:---check}
case "$mode" in --check|--install) ;; *) echo 'Usage: sh deploy/install_bundle.sh --check | --install --idle-confirmed [--replace-startup]' >&2; exit 2;; esac
sha256sum -c SHA256SUMS
[ -f instrument_app ] && [ -f luckfox_mux_adapter.so ] && [ -f deploy/RkLunch.sh ]
[ -f deploy/button_inputs.sh ] && [ -f deploy/S79buttons ] && [ -f deploy/wpa_supplicant.default.conf ]
[ "$(find sounds -name '*.wav' -type f | wc -l)" -eq 20 ]
if [ "$mode" = --check ]; then
    echo 'CHECK_OK: bundle integrity only; no installation or service restart.'
    exit 0
fi
[ "${2:-}" = --idle-confirmed ] || { echo 'Stop capture/diagnostics/uploads first, then pass --idle-confirmed.' >&2; exit 2; }
[ "$(id -u)" = 0 ] && [ "$(uname -m)" = armv7l ] || { echo 'Requires root on ARMv7 Luckfox.' >&2; exit 2; }
grep -q 'Luckfox Pico Zero' /proc/device-tree/model || { echo 'This startup is for Pico Zero only.' >&2; exit 2; }
for command in tar sha256sum pidof awk df sync cmp du aplay amixer devmem; do command -v "$command" >/dev/null; done
[ -x /oem/usr/bin/rkipc ] && [ -e /lib/ld-uClibc.so.0 ] && [ -f /RkLunch.sh ]
[ -f /opt/instrument/config.json ] || { echo 'Missing local config.json; initialize and review it manually. Never overwrite existing config.' >&2; exit 2; }
./instrument_app --check-config /opt/instrument/config.json
[ "$(./instrument_app --version)" = "$(cat VERSION)" ]
for service in instrument_app rkipc aplay; do
    if pidof "$service" >/dev/null 2>&1; then echo "Still running: $service. Installation refused." >&2; exit 2; fi
done
if [ -d /opt/instrument/capture/writing ] && [ -n "$(ls -A /opt/instrument/capture/writing)" ]; then
    echo 'capture/writing is nonempty; investigate unfinished recording, do not delete it.' >&2; exit 2
fi
startup_old=$(sha256sum /RkLunch.sh | awk '{print $1}')
startup_new=$(sha256sum deploy/RkLunch.sh | awk '{print $1}')
if [ "$startup_old" != "$startup_new" ] && [ "${3:-}" != --replace-startup ]; then
    echo 'RkLunch.sh differs (possibly custom UVC/network startup). Review differences, then explicitly pass --replace-startup.' >&2
    exit 2
fi
run=$(date -u +%Y%m%dT%H%M%SZ)-$$
record=/opt/instrument/backups/bundle-$run
mkdir -p "$record"
chmod 700 "$record"
echo "RECORD=$record"
exec >"$record/install.log" 2>&1
trap 'result=$?; trap - EXIT; printf "exit_code=%s\n" "$result" > "$record/result.txt"; sync; exit "$result"' EXIT
printf 'board_utc=%s\nversion=%s\npackage=%s\n' "$(date -u)" "$(cat VERSION)" "$package" >"$record/before.txt"
uname -a >>"$record/before.txt"
cat /proc/device-tree/serial-number >>"$record/before.txt"
df -k / /opt /tmp >>"$record/before.txt"
ps >>"$record/before.txt"
cp /opt/instrument/config.json "$record/config-before.json"
chmod 600 "$record/config-before.json"
cp SHA256SUMS "$record/package-SHA256SUMS"
printf 'instrument_app opt/instrument/bin/instrument_app\nluckfox_mux_adapter.so opt/instrument/bin/luckfox_mux_adapter.so\ndeploy/RkLunch.sh RkLunch.sh\ndeploy/S80instrument oem/usr/etc/init.d/S80instrument\nVERSION opt/instrument/installed-version\nBUILD.txt opt/instrument/installed-build.txt\n' >"$record/install-map.txt"
printf 'deploy/button_inputs.sh opt/instrument/bin/button_inputs.sh\ndeploy/S79buttons oem/usr/etc/init.d/S79buttons\n' >>"$record/install-map.txt"
# Initialize factory Wi-Fi only. Existing real networks are preserved.
printf 'deploy/wpa_supplicant.default.conf opt/instrument/defaults/wpa_supplicant.conf\n' >>"$record/install-map.txt"
if [ ! -f /userdata/wpa_supplicant.conf ]; then
    printf 'deploy/wpa_supplicant.default.conf userdata/wpa_supplicant.conf\n' >>"$record/install-map.txt"
elif [ "$(grep -c '^[[:space:]]*ssid=' /userdata/wpa_supplicant.conf)" -eq 1 ] && grep -q '^[[:space:]]*ssid="Your SSID"' /userdata/wpa_supplicant.conf; then
    printf 'deploy/wpa_supplicant.default.conf userdata/wpa_supplicant.conf\n' >>"$record/install-map.txt"
fi
# Factory rkwifi startup can restore /data from /etc; preserve the real network there too.
if [ ! -f /etc/wpa_supplicant.conf ] || { [ "$(grep -c '^[[:space:]]*ssid=' /etc/wpa_supplicant.conf)" -eq 1 ] && grep -q '^[[:space:]]*ssid="Your SSID"' /etc/wpa_supplicant.conf; }; then
    wifi_source=deploy/wpa_supplicant.default.conf
    if [ -f /userdata/wpa_supplicant.conf ] && grep -q '^[[:space:]]*ssid=' /userdata/wpa_supplicant.conf && ! grep -q '^[[:space:]]*ssid="Your SSID"' /userdata/wpa_supplicant.conf; then
        wifi_source=/userdata/wpa_supplicant.conf
    fi
    printf '%s etc/wpa_supplicant.conf\n' "$wifi_source" >>"$record/install-map.txt"
fi
for source in sounds/*.wav; do printf '%s opt/instrument/%s\n' "$source" "$source"; done >>"$record/install-map.txt"
: >"$record/existing-files.txt"
: >"$record/new-files.txt"
: >"$record/before-SHA256SUMS"
set --
while read -r source destination; do
    if [ -L "/$destination" ]; then echo "Unexpected symlink: /$destination"; exit 2; fi
    if [ -f "/$destination" ]; then
        printf '%s\n' "$destination" >>"$record/existing-files.txt"
        sha256sum "/$destination" >>"$record/before-SHA256SUMS"
        set -- "$@" "$destination"
    elif [ -e "/$destination" ]; then
        echo "Unexpected destination type: /$destination"; exit 2
    else
        printf '%s\n' "$destination" >>"$record/new-files.txt"
    fi
done <"$record/install-map.txt"
# Require room for new payload, old-file backup and temporary copies.
needed=$(du -sk "$package" | awk '{print $1}')
old=0
for destination in "$@"; do size=$(du -k "/$destination" | awk '{print $1}'); old=$((old + size)); done
available=$(df -k /opt/instrument | awk 'END {print $4}')
[ "$available" -gt $((needed * 2 + old + 5120)) ] || { echo 'Insufficient disk space; nothing overwritten.'; exit 2; }
if [ "$#" -gt 0 ]; then tar -cf "$record/rollback-files.tar" -C / "$@"; else touch "$record/NO_PREVIOUS_FILES"; fi
sync
: >"$record/after-SHA256SUMS"
while read -r source destination; do
    mkdir -p "$(dirname "/$destination")"
    cp "$source" "/$destination.bundle-new"
    case "$destination" in */wpa_supplicant.conf) chmod 600 "/$destination.bundle-new";; */instrument_app|*/button_inputs.sh|RkLunch.sh|*/S79buttons|*/S80instrument) chmod 755 "/$destination.bundle-new";; *) chmod 644 "/$destination.bundle-new";; esac
    expected=$(sha256sum "$source" | awk '{print $1}')
    actual=$(sha256sum "/$destination.bundle-new" | awk '{print $1}')
    [ "$expected" = "$actual" ]
    sync
    mv "/$destination.bundle-new" "/$destination"
    sha256sum "/$destination" >>"$record/after-SHA256SUMS"
done <"$record/install-map.txt"
sha256sum -c "$record/after-SHA256SUMS"
# Config, pairing, state, pending recordings, Wi-Fi and camera config are not copied.
cmp /opt/instrument/config.json "$record/config-before.json"
printf 'board_utc=%s\n' "$(date -u)" >"$record/after.txt"
/opt/instrument/bin/instrument_app --version >>"$record/after.txt"
df -k /opt >>"$record/after.txt"
sync
echo 'INSTALL_OK: files installed and verified. Reboot manually, then check runtime and record acceptance.'