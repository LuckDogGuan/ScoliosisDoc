param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$voice.SelectVoice('Microsoft Huihui Desktop')
$voice.Rate = 0
$voice.Volume = 100
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$phrases = [ordered]@{
    boot_ready='设备已启动'
    capture_enabled='拍摄已启用'
    capture_disabled='拍摄已停止'
    capture_start='开始拍摄'
    capture_done='拍摄完成'
    capture_short='录像过短，请重拍'
    capture_failed='拍摄失败，请重拍'
    pair_window='已进入配对模式'
    pair_window_closed='配对模式已关闭，已恢复正常模式'
    pair_success='连接成功'
    pair_failed='连接失败'
    pair_disconnected='设备已断开连接'
    please_connect='请在电脑上连接设备'
    uploaded='视频已上传'
    saved_on_device='视频已保存在设备'
    storage_low='存储空间不足'
    wifi_connected='网络已连接'
    wifi_disconnected='网络已断开'
    wifi_recovering='网络重连中'
    wifi_attention='网络异常，请检查路由器'
    wifi_restored='网络已恢复'
    volume_test='设备音量测试'
}
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
try {
    foreach($item in $phrases.GetEnumerator()) {
        $voice.SetOutputToWaveFile((Join-Path $OutputDirectory ($item.Key+'.wav')),$format)
        $voice.Speak($item.Value)
        $voice.SetOutputToNull()
    }
    $phrases | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'phrases.json') -Encoding utf8
    Write-Output ('Generated '+$phrases.Count+' consistent Huihui prompts')
} finally { $voice.Dispose() }
