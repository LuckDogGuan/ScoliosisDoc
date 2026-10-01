param(
    [string]$OutputDirectory = 'D:/code/Scoliosis/Luckfox/调试/声音/拍摄改造_2026-10-01'
)

# Offline Windows voice; explicit UTF-8 loading also supports Windows PowerShell 5.
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$voice.SelectVoice('Microsoft Huihui Desktop')
$voice.Rate = 0
$voice.Volume = 100
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$phrases = [ordered]@{
    capture_start = '开始录制'
    capture_short = '录像过短，请重新拍摄'
    capture_enabled = '拍摄已启用，请按住左右按键开始录像'
    capture_disabled = '拍摄已停止'
    wifi_recovering = '无线网络连接不稳定，正在自动重连'
    wifi_attention = '无线网络无法恢复，请检查路由器'
    pair_window = '配对窗口已开启，请在电脑上选择仪器'
    wifi_restored = '仪器无线网络已恢复'
}
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
try {
    foreach ($item in $phrases.GetEnumerator()) {
        $path = Join-Path $OutputDirectory ($item.Key + '.wav')
        $voice.SetOutputToWaveFile($path, $format)
        $voice.Speak($item.Value)
        $voice.SetOutputToNull()
        Write-Output "$($item.Key): $($item.Value)"
    }
} finally {
    $voice.Dispose()
}
