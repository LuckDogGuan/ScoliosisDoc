param(
    [Parameter(Mandatory = $true)]
    [string]$Name
)

$ErrorActionPreference = "Stop"
$adb = Join-Path $PSScriptRoot "adb.ps1"
$preferred = "3253c006806f5194"
$serials = @()
foreach ($line in (& $adb devices)) {
    if ($line -match '^(\S+)\s+device(\s|$)') {
        $serials += $Matches[1]
    }
}
if ($serials -contains $preferred) {
    $serial = $preferred
} elseif ($serials.Count -eq 1) {
    $serial = $serials[0]
} else {
    throw "adb device not ready: $($serials -join ', ')"
}
$root = Split-Path $PSScriptRoot -Parent
$ini = (Get-ChildItem -LiteralPath $root -Recurse -Filter $Name -File | Select-Object -First 1).FullName
if (-not $ini) {
    throw "preset not found: $Name"
}

& $adb -s $serial shell "killall -9 rkipc; sleep 1; pidof rkipc || echo stopped"
& $adb -s $serial push $ini /userdata/rkipc.ini
& $adb -s $serial shell "setsid /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/rkipc-fps.log 2>&1 < /dev/null & sleep 2; iw dev wlan0 set power_save off; pidof rkipc || echo not-running; grep -E 'num is|framerate' /tmp/rkipc-fps.log; dmesg | grep 'fps fix' | tail -n 1"
