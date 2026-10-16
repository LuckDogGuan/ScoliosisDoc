# 下位机 3.3.15 语音恢复与烧录记录（2026-10-16）

目标 CAM-211ec7045815bf02，Wi-Fi 192.168.101.7，运行构建 f13fdbe42bae。
本次只修改下位机，移除 3.3.12 / f94bea2 引入的全局语音白名单，不再漏掉既有配对和拍摄启停提示。
PC“从此位置开始拍摄”原本就调用 startCapture -> capture_enable，接受后下位机已有 capture_enabled 触发；
本次恢复该通路，无需修改上位机或新增重复提示。

## 语音边界

现有事件重新可入队，包括进入配对、配对成功、解除配对、关闭配对模式、拍摄已启用／停止、
上传成功及保存到仪器等。全部 22 个现有 WAV 资源名已逐项检查可入队。
只恢复已有业务触发，不凭空增加尚无触发点的播报。
保留八条队列容量、平台音频资源校验、独立播放进程、拍摄开始提示优先、
PC 语音交接、指令幂等和语音失败不阻塞拍摄。未改 WAV、音量、相机配置和拍摄时序。

## 验证与部署

- 修复前新回归明确失败：启动／全部资源模式被过滤，真实 UDP pair_commit 成功却没有提示入队。
- 修复后 7 项主机回归通过：资源与网络状态、真实 UDP 配对／启停／解除、拍摄节奏、
  开机语音隔离、语音失败继续拍摄、语音焦点，以及配对窗口开关／超时。
- 全部 22 种资源通过，队列容量保护仍有效；重复成功请求、capture_renew 和未授权指令不新增播报。
- ARM -Wall -Wextra -Werror、包内及外层校验通过；源码提交 f13fdbe，归档 1c3f59c，tag instrument-v3.3.15。
- USB 当时无设备，按固定 SSH 指纹、芯片序列号、应用 ID 与 wlan0 地址交叉核验原仪器后，
  通过现有 Wi-Fi 安装器备份、安装并软件重启；实际版本／构建／部署文件及原配置、配对、Wi-Fi 保持校验通过。
- 实板沿用原配对，发送与 PC 按钮相同的 capture_enable，采集实际 aplay 命令：
  capture_enabled.wav（拍摄已启用）、capture_disabled.wav（拍摄已停止），各一次成功完成。
  两条指令分别原包重复发送，仍只各播一次；没有准备学生或启动录像。
- 结束后 idle、许可关闭、audio_busy=false、正常 GPIO，无 INSTRUMENT_BUTTON_FILE。
  原配对文件哈希前后相同；旧三份失败录像保留；相机路径 /video0，RTSP 可读。
- 本轮没有改变原业务配对来做新的实板开窗／解除循环；配对语音验证采用既有调用检查、
  全资源和实际 UDP 主机回归。扬声器实际听感需现场确认。
- 本轮不新增五轮录像或断电冷启动验收；RTSP 包计数不冒充全帧解码。

## 分类证据

| 分类 | 文件 |
|---|---|
| 安装前状态与身份 | before-state.json、before.json |
| 安装／重启校验 | install-cli.txt、install-verification.json |
| 实际启用／停止播放与重复请求 | capture-session-audio.json |
| 相机连通性 | camera-rtsp.txt |
| 版本、哈希与回退 | release.json |
| 汇总 | VALIDATION.json |

完整私有安装日志和备份审计在 release.json 的 installer_report；不将配置、密码或备份归档提交 Git。
正式包唯一在 WSL /home/guanjx/luckfox/Scoliosis/releases/3.3.15，不添加 Windows 固件副本。
原生上位机窗口及真实学生数据未操作，上位机源码未变。没有新建分支或工作树。

GitNexus 编辑前 queue_sound 为 HIGH，10 个直接调用点，已报告并检查。
提交前报告 LOW 未映射仅删除的 queue_sound 白名单行，已按真实 WSL diff 人工复核共享入口与各调用；
测试必须明确验证“有声音进入队列”，不能只检查配对／启用业务成功。归档另外逐文件和哈希核对。

## 回退

安装器板端备份：/opt/instrument/backups/bundle-20261016T022815Z-3758/rollback-files.tar。
关闭许可，确认拍摄、上传、诊断和声音结束后停业务／相机服务，按安装映射只恢复备份程序／声音／启动文件；
保留业务数据、配对、Wi-Fi 及相机 mount_path=/。回退到 3.3.14 将重新屏蔽配对／拍摄启停语音。
软件修复可通过单独回退 f13fdbe 实现，先核对当前版本及后续改动，不重置其他工作。
