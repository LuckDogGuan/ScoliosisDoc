param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output already exists; preserve prior assets.' }
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
Add-Type -AssemblyName System.Speech
$deviceVoice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$deviceVoice.SelectVoice('Microsoft Kangkang')
$deviceVoice.Rate = -1
$deviceVoice.Volume = 100
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$source = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'generate_stability_sounds.ps1'), [Text.Encoding]::UTF8)
$phrases = [ordered]@{}
foreach ($match in [regex]::Matches($source, "(?m)^\s*(\w+)='([^']+)'")) { $phrases[$match.Groups[1].Value]=$match.Groups[2].Value }
if ($phrases.Count -ne 22) { throw 'Expected exactly 22 current phrases.' }
try {
  foreach ($item in $phrases.GetEnumerator()) {
    $deviceVoice.SetOutputToWaveFile((Join-Path $OutputDirectory ($item.Key+'.wav')), $format)
    $deviceVoice.Speak($item.Value)
    $deviceVoice.SetOutputToNull()
    Write-Host ('Generated '+$item.Key)
  }
  $phrases | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'phrases.json') -Encoding utf8
} finally { $deviceVoice.Dispose() }
