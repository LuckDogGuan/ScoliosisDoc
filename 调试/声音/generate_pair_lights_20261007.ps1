Add-Type -AssemblyName System.Speech
$taskVoice=[System.Speech.Synthesis.SpeechSynthesizer]::new()
$taskVoice.SelectVoice('Microsoft Huihui Desktop')
$taskFormat=[System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$taskSounds='D:\code\Scoliosis\Luckfox\调试\声音\配对灯光_2026-10-07'
[IO.Directory]::CreateDirectory($taskSounds) | Out-Null
try {
  $taskPhrases=@{pair_window='已进入配对模式，请在电脑上选择仪器。四十五秒后自动退出。';pair_window_closed='配对模式已关闭，已恢复正常模式。'}
  foreach($taskItem in $taskPhrases.GetEnumerator()) {
    $taskVoice.SetOutputToWaveFile((Join-Path $taskSounds ($taskItem.Key+'.wav')),$taskFormat)
    $taskVoice.Speak($taskItem.Value)
    $taskVoice.SetOutputToNull()
    Write-Output $taskItem.Key
  }
} finally {$taskVoice.Dispose()}