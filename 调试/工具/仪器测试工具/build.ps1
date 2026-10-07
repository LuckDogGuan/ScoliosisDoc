param(
    [string]$Python = 'C:\Program Files\Python312\python.exe',
    [string]$AdbDir = 'D:\SoftWare\Android_Studio_SDK\platform-tools'
)
$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
$payload = Join-Path $toolRoot 'payload'
$manifest = Get-Content -LiteralPath (Join-Path $payload 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($property in $manifest.files.PSObject.Properties) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $payload $property.Name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $property.Value) { throw "Payload hash mismatch: $($property.Name)" }
}
$buildRoot = Join-Path $toolRoot '.build'
$releaseRoot = Join-Path $toolRoot 'release'
New-Item -ItemType Directory -Force -Path $buildRoot,$releaseRoot | Out-Null
$argsForBuild = @('-m','PyInstaller','--noconfirm','--onefile','--windowed',
    '--name','仪器测试工具','--distpath',$releaseRoot,'--workpath',(Join-Path $buildRoot 'work'),
    '--specpath',$buildRoot,'--add-data',"$payload;payload",'--collect-submodules','pygrabber',
    '--collect-submodules','comtypes.gen','--exclude-module','comtypes.test')
foreach ($name in @('adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll')) {
    $path = Join-Path $AdbDir $name
    if (-not (Test-Path -LiteralPath $path)) { throw "Build input missing: $path" }
    $argsForBuild += @('--add-binary',"$path;adb")
}
& $Python @argsForBuild (Join-Path $toolRoot '仪器测试工具.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$exe = Join-Path $releaseRoot '仪器测试工具.exe'
Get-FileHash -LiteralPath $exe -Algorithm SHA256
