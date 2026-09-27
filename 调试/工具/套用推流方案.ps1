param(
    [Parameter(Mandatory = $true)]
    [string]$Name
)

$ErrorActionPreference = "Stop"
$serial = "3253c006806f5194"
$root = Split-Path $PSScriptRoot -Parent
$ini = (Get-ChildItem -LiteralPath $root -Recurse -Filter $Name -File | Select-Object -First 1).FullName
if (-not $ini) {
    throw "preset not found: $Name"
}

adb -s $serial shell "killall -9 rkipc; sleep 1; pidof rkipc || echo stopped"
adb -s $serial push $ini /userdata/rkipc.ini
adb -s $serial shell "setsid /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/rkipc-fps.log 2>&1 < /dev/null & sleep 2; iw dev wlan0 set power_save off; pidof rkipc || echo not-running; grep -E 'num is|framerate' /tmp/rkipc-fps.log; dmesg | grep 'fps fix' | tail -n 1"
