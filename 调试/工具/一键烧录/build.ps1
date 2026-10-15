param(
    [string]$Python = 'C:\Program Files\Python312\python.exe',
    [string]$AdbDir = 'D:\SoftWare\Android_Studio_SDK\platform-tools'
)
$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
if ((Get-FileHash -LiteralPath (Join-Path $toolRoot 'payload/udp_query') -Algorithm SHA256).Hash.ToLower() -ne '6f653c5f0f064c169d4b640e5284674f450a67b7181e6f8e300c8ed7607d35ca') {
    throw 'Runtime payload hash mismatch'
}
$buildRoot = Join-Path $toolRoot '.build'
$releaseRoot = Join-Path $toolRoot 'release'
New-Item -ItemType Directory -Force -Path $buildRoot,$releaseRoot | Out-Null
$buildArgs = @('-m','PyInstaller','--noconfirm','--onefile',
    '--distpath',$releaseRoot,'--workpath',(Join-Path $buildRoot 'work'),
    '--specpath',$buildRoot,'--add-data',"$(Join-Path $toolRoot 'payload');payload")
foreach ($name in @('adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll')) {
    $path = Join-Path $AdbDir $name
    if (-not (Test-Path -LiteralPath $path)) { throw "Build input missing: $path" }
    $buildArgs += @('--add-binary',"$path;adb")
}
foreach ($target in @(
    @{Name='下位机一键烧录'; Mode='--windowed'},
    @{Name='下位机烧录CLI'; Mode='--console'}
)) {
    & $Python @buildArgs $target.Mode '--name' $target.Name (Join-Path $toolRoot 'flash_tool.py')
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $($target.Name)" }
    Get-FileHash -LiteralPath (Join-Path $releaseRoot ($target.Name + '.exe')) -Algorithm SHA256
}
