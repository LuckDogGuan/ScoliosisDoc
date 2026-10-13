# 2026-10-13 自动验收工具

正式下位机源码和包只在 WSL `/home/guanjx/luckfox/Scoliosis`。本目录保存 Windows 调试脚本和证据，不复制下位机包或源码。测试名单和视频只在 Flutter `build/stability-board-*` 独立目录；不使用真实学生名单。

## 常用入口

| 入口 | 用途与约束 |
|---|---|
| `调试/工具/Python中间层/usb_debug_transport.py` | 显式 `--serial --device --log`；通过 ADB 固定 SSH 主机公钥，控制和视频两个独立连接，HTTP 18085、上位机 8081。可选 `--fault-config --fault-log` 启用身份限定、有期限的故障注入。没有策略文件不注入故障。|
| `run_board_validation.py` | 显式 serial/device/button-file/data-root，独立名单，自动模拟按键，至少20轮且有限一小时；完整解码、时长、大小及SHA256。|
| `run_fault_validation.py` | 同样显式目标；实际暂时静音 Windows，执行 Flutter `tool/capture_stability_fault_test.dart`。默认60分钟，正常/异常退出都恢复原Windows静音与音量状态。脚本最后在同一播报实例恢复声音拍3段。|
| `monitor_stability.py` | 只读，`--interval 300 --minutes 70`；evidence须指向 `stability-evidence.jsonl`，不续租、不模拟按键。检查学生/轮次/解码/时长/哈希/设备音量10/待传/许可/boot/系统音频。声明的进程重启与非预期内核变化分开。|
| `crash_restart_for_test.py` | 只在匹配serial、device、capture-id、binary SHA且正录像时SIGKILL主协调进程；确认相机停止、RKiPC和内核未重启、原片仍在，绝不按进程名批量杀进程。|
| `finalize_board_runtime.py` | 默认只读校验正式包及实板26个有效负载文件。`--apply`仅在空闲、许可关、未配对、待传零时恢复备份配置/配对，唯一配置改动为音量10，写入正式版本元数据，再通过既有S80入口启动无模拟输入的正常程序。保留前后备份，不删除视频。|
| `windows_audio_fact_test.py` | `--read-only`查询真实CoreAudio状态；默认有限语音验证覆盖静音、音量零、恢复。记录软件执行结果，不代替人耳听感。|
| `test_usb_fault_transport.py` | 本地socket HTTP重放，验证普通转发、开录通知丢失、完成响应仅丢一次、半包及重试；不连设备。|
| `package_windows_release.py --version 3.3.9` | 要求已提交、工作树无已跟踪改动；完整87文件目录、zip读回、原生库SHA校验、生成release.json和INDEX。既有归档不能覆盖。|

主测试需先启动上述中间层，且设备必须处于测试runtime（`INSTRUMENT_BUTTON_FILE=/tmp/stability-buttons-20261013`）。只在现场授权的唯一仪器上使用；脚本主动核对目标，不依赖tmux/设备昵称。操作结束执行正常runtime恢复。

## 日志和失败边界

- `board-volume10-soak.log`：早期3.3.8/上位机3.3.6完整一小时181段通过；对应独立volume10-final目录。
- `board-faults-duration-boundary.log`：前5种通过，真实60001ms暴露过严60秒校验，失败记录保留。
- `board-faults-shared-ssh-boundary.log`：调试控制和旧待传视频共用SSH连接造成控制延迟、许可过期；不能计为静音根因或一小时通过。
- `board-faults-soak.log`：当前RUN_STATUS对应活动阶段；最终结果以其独立数据目录的`passed`行和实际elapsed>=3600000为准。
- `monitor-5min*.jsonl`：每300秒检查；启动路径修正、源码切换、主动暂停、故障注入与真实异常分别在WORKLOG说明。
- `development_deploy.py`、`development-deploy*`、`refresh_development_binary.py`、早期`*-pause.json`是本次设备首次部署/迭代历史，不作为其他仪器通用安装器。首次部署记录中的单PID假定仅对旧3.3.7成立；现应使用hello.application_pid识别主协调进程。

故障策略和音频恢复状态 `*.local.json` 仅本机保存，不提交。真实学生名单、录像、Wi-Fi密码或SSH认证材料不进入交付Git记录。

全量Flutter测试需 `flutter test --no-pub --concurrency=1 --reporter expanded`：多个测试文件模拟固定UDP37020，不能并发争用此端口。并发套件的一次端口干扰失败日志已保留；不得把它计为通过。
