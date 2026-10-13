$ErrorActionPreference = 'Stop'
$url = 'http://127.0.0.1:8766'
try {
    $reply = Invoke-RestMethod "$url/api/adc" -TimeoutSec 6
    if ($reply.service -ne 'luckfox-adc') { throw 'Port 8766 is used by another service.' }
} catch {
    if (Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue) { throw }
    $python = (Get-Command python.exe).Source
    Start-Process -FilePath $python -ArgumentList @('"' + (Join-Path $PSScriptRoot 'server.py') + '"') -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        if (Test-NetConnection 127.0.0.1 -Port 8766 -InformationLevel Quiet -WarningAction SilentlyContinue) { break }
    }
}
Start-Process $url
