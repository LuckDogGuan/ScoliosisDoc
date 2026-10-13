# Windows 实际静音语音验收

2026-10-13 实际使用 Flutter `WindowsSapiSpeaker`，固定测试短句，不使用真实人员姓名。系统音频修改通过普通用户的 CoreAudio endpoint 接口；没有安装新依赖、停用音频服务、禁用设备或请求人工操作。

## 已验证

原系统静音为 `false`，主音量 scalar 为 `0.10003136843442917`。依次设为正常、系统静音、音量 0、恢复声音，实际核对每一阶段前后系统状态不被语音接口修改。每阶段执行以下四项：

- 固定短句播报在有限时间内结束。
- 1800 ms 后取消长句；`stop()` 在 2000 ms 内返回，原 `speak()` 也结束。
- 取消后新的短句可以正常结束。
- 新短句替换长句，旧请求结束，不阻塞新请求。

四种状态共 16 项实际测试均通过。短句耗时约 2.3–2.9 秒；测试期间 50 ms 定时器持续运行，证明 Dart 事件循环有响应。

追加同一 Flutter 进程、同一个真实 `WindowsSapiSpeaker` 实例的连续状态变化：系统静音 → 主音量 0 → 恢复声音，各次新的播报均结束。这个恢复结果不依赖重启 Flutter 或重建 speaker。测试前后均实际读回系统状态。

`finally` 已恢复原系统静音和原音量；测试结束后再次通过独立进程读取，仍为 `false` / `0.10003136843442917`。具体耗时、事件循环 ticks 和系统状态见 `windows-audio-facts/*.jsonl`、`windows-audio-facts/summary.json`、`windows-audio-transitions/summary.json`。

原有 `test/speech_stability_test.dart` 的四项注入回归也实际运行通过：语音进程不结束时 stop 可取消、延迟启动不会播报过期文本、超时杀掉工作进程并允许下一请求、音频不可用返回失败后下一请求可恢复。

## 证据边界

本次证明真实系统静音及真实 0 音量不会挂住语音接口，并证明恢复声音后相同对象接受新请求。没有声学监听或人工听感证据；不把进程成功结束称为喇叭实际发声已验收。

没有移除默认输出设备或停止音频服务，因此“真实硬件输出不可用”未验收。该失败处理由上述非零退出和超时注入回归覆盖；设备/服务禁用会扩大系统影响，本次按授权限定不执行。

## 可复用入口

实际 Flutter 入口为 `ScoliosisFlutter/tool/windows_speech_fact_test.dart`。`windows_audio_fact_test.py --read-only` 仅查询系统状态；无该标志会临时切换四种状态并在结束/异常时恢复原值，再执行同一实例的状态转换测试。可用 `--transitions-only` 仅运行同一实例转换。每次使用新 `--evidence-root` 保留独立记录。

接口依据为微软的 [IMMDeviceEnumerator::GetDefaultAudioEndpoint](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-immdeviceenumerator-getdefaultaudioendpoint)、[IAudioEndpointVolume](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume) 和 [SetMute](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-setmute)。只使用读取、静音和主音量 scalar 控制。
