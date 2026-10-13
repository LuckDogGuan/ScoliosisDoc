# 拍摄链路稳定性修复与验收记录

更新日期：2026-10-13。**已按用户最新要求结束约20分钟最终验收并恢复正常运行。** 设备音量已保存为10；背光代码和设置保持原状。所有按键均由脚本自动触发，独立名单不含真实学生。

## 实施结果

| 问题 | 修复后的行为 |
|---|---|
| 下位机开录等待提示音，音频失败阻止录像 | 开录不等待语音；提示音独立进程有期限，缺文件/失败/阻塞不挡拍摄。旧提示不能延迟下一轮。|
| 原生Windows语音可无限等待 | 保留NameSpeaker接口，Huihui独立可终止语音进程，启动5秒/播报15秒/停止1秒限期，最新请求优先。设置先保存再停止，系统静音保持静音。|
| 开录通知丢失后计时不显示、收尾归零 | V3查询可选拍摄快照回补已有匹配关联，单调计时，收尾冻结；页面保留上一轮最终时长/人员/上传状态，60秒进度封顶。旧固件继续支持。|
| 断线后迟到结果不能切人 | 完成结果持久化、幂等切人，上传后台继续；旧许可失效后只更新人员，不建立下一轮关联，显示“继续拍摄”，确认后恢复。|
| 重启完成通知先于hello | HTTP完成检测boot变化先暂停旧许可；原人员结果仍持久化，确认前不自动prepare。自动prepare失败也显示可恢复操作。|
| 续租被普通控制请求排队拖住 | 优先续租、合并重复请求；序号按实际发送生成，许可仍6秒。诊断日志移出关键等待。|
| 设备事件目录扫描/主循环阻塞使按住变无效 | 完成事件扫描移至有限后台任务；独立10ms按键采样，不改物理按键许可/全释放校验。停止采样或原始读取失败仍拒绝危险输入。|
| 异常录像与业务进程重启 | 下次开录前必须确认相机已停止。主/子进程及退出、相机RPC、开停录、许可、事件日志区分业务boot/内核boot。中断录像失败结果不冒充成功或录像过短。|
| JSON/视频半包和退出挂住 | JSON5秒空闲/10秒总，视频65秒空闲/300秒总；流式背压，仅清理本次.part。设备原片/待传关联保留并重试。退出先保存准备，失败保留刷新通信、允许重试；关闭阶段取消接收并有限等待。|

下位机提示统一为离线Microsoft Huihui、正常语速、16kHz单声道16bit PCM。启动初始化完成即播“设备已启动”，不等Wi-Fi。常用开始/完成/启用/停止等已缩短；配对关闭为“配对模式已关闭，已恢复正常模式”。22个WAV文本、时长、SHA见WSL正式包 `sounds/stability-voice-manifest.json`。物理喇叭听感未由软件结果替代。

## 分类证据

### 真实复现并修复

- 下位机播放失败阻止开录、原语音停止无限等待：定向回归及受限子进程测试。
- 当前实板拍摄第二轮按键失败：主循环事件扫描>100ms，背光同步调用也可超过100ms；保留背光，用独立采样隔离后连续拍摄。早期失败日志 `round2-failure-board.jsonl`、`gap-failure-board.jsonl`。
- nominal60秒完成实际60001ms：原完成查询60000校验过严；改为65000安全上限，原时长不伪造，显示仍60秒封顶。`board-faults-duration-boundary.log`、`duration-boundary-green.log`。
- SIGKILL后HTTP失败结果先于新hello：旧许可误尝试prepare，继续提示时序错误；实板证据 `board-faults-http-restart-boundary.log`，回归 `restart-http-before-query-red.log` / `restart-http-before-query-green.log`。
- USB调试控制/大视频共用SSH传输造成3.5秒延迟及6276ms租期过期：`board-faults-shared-ssh-boundary.log`。调试工具拆分固定主机公钥的控制/上传SSH连接并记录control_elapsed_ms；未加长许可。

### 注入与软件验收

- 上位机3.3.9：87项全量测试通过、analyze无问题；含语音永不返回、音频进程超时/取消/迟启动、查询回补、完成响应丢失、排队续租、退出保存失败和半包接收等。
- 测试文件多个模拟固定UDP37020，全量以 `--concurrency=1` 隔离端口。一轮默认并发端口争用失败日志单独保存为 `flutter-full-test-v339-parallel.log`，未冒充通过。
- 实际Windows语音：正常、真实系统静音、音量零、恢复4种状态16项通过；同一speaker连续恢复通过。见 `Windows实际静音语音验收.md` 和 `windows-audio-facts/`、`windows-audio-transitions/`。
- 下位机host/check-host、播放失败、进程组终止、异常相机停止确认、事件扫描阻塞、独立按键采样失效/重建/关闭、Wi-Fi维护阻塞不拖启动语音、启动恢复定向测试通过。见 `firmware-final-tests.log`、`firmware-checks.json` 及 `startup-recovery-*`。
- 正式包和实板程序/适配器/启动/22语音共26个文件逐字节SHA一致：`formal-board-payload-preflight.json`。

### 实板连续运行

| 阶段 | 结果 |
|---|---|
| FW3.3.8 / App3.3.6、音量10、正常拍摄上传 | 已通过：181段，实际3609422ms；逐段全帧解码、大小、SHA、归属、时长相差<1秒。`board-volume10-soak.log`、`monitor-5min.jsonl`。|
| 早期47轮、预冻结17轮 | agent因用户音量要求或启动语音修复主动暂停，未计一小时通过。|
| 故障迭代的5段/1段/6段 | 发现边界或时序问题并保留失败，不计最终通过。|
| FW3.3.9 / App3.3.9、真实Windows静音、7种故障及持续拍摄 | 用户将最终时间改为20分钟，已按新条件验收：57段、实际1291609ms（21.53分钟含收尾），98,090,626字节，全部完整解码并读回SHA，最大时长差34ms。`accepted-20minute-validation.json`。|

用户中途改变验收时长，原60分钟runner无法改变已启动进程的环境参数；agent关闭许可后，其下一轮prepared等待超时并退出，日志保留，**不把runner退出码1改写成自然PASS，也不把此次主动停止当业务故障**。20分钟结论来自57段完整证据及外部逐文件读回校验。按新要求未继续最终一小时，也未执行该轮预定的恢复声音后3段；同一speaker恢复已由此前实际Windows连续音频状态测试验证。

每300秒只读检查 `monitor-5min-verified.jsonl`：轮次、唯一关联、时长、视频SHA/大小/帧数、device volume/saved_volume=10、待传、许可、业务boot/内核boot、Windows静音。声明的SIGKILL业务boot变化单独记录，不能算设备意外重启。最终已停止监控并暂停5分钟提醒，USB中间层及自建转发已关闭；独立相机RPC读回recording=0，自建临时模拟文件已移除，原模拟状态文件不动。

## 发布与可追溯性

所有仓库工作分支为 `codex/capture-stability-20261013`；没有推送、合并或覆盖历史发布。

| 交付 | 源码与归档 |
|---|---|
| 下位机3.3.9 | WSL `/home/guanjx/luckfox/Scoliosis`；核心61870f3、恢复修复9a5af83、归档e2a5ee6，tag `instrument-v3.3.9`。正式包 `/home/guanjx/luckfox/Scoliosis/releases/3.3.9/instrument-v3.3.9.tar.gz`。|
| 下位机包SHA256 | `3fc21b58f64a8abb8f08eb59ded5e140e22521a12f4da37bb3f63608f9c41aaf` |
| 实板程序SHA256 | `e4466b57a3349e83ff4744cac1e02c41a010be82482aff1f3f46ad09e7fe3849` |
| 上位机3.3.9+20261013 | 业务源ae13512；业务源ae13512、正式归档2cccca5；完整87文件 `D:/code/Scoliosis/ScoliosisFlutter/releases/windows-3.3.9-ae13512-20261013`。ZIP SHA256 `3ad0f9698aad4cf64ebd3d3f462604a0461a8a134ab29d21b64c4e166e0670bc`，详见release.json。|
| Windows调试工具 | Luckfox提交e7d1b0e；显式serial/device、只读五分钟监控、注入/自动按键/恢复脚本；工具说明 `TOOLS.md`。|

GitNexus实施前刷新且逐符号impact；语音/控制核心CRITICAL已在修改前告知并重点回归，背光修改撤回。每个提交前执行detect_changes；WSL以真实仓库Git差异映射索引，避免把临时源码索引当权威工程。

## 恢复与回退

当前测试仪器 serial `3253c006806f5194` / device `CAM-000123`。原3.3.7程序SHA `33cb2d4fc887948097ef4878589dad52aaa8158390c187c0b397315caaddfe01`；原二进制、22语音中的原文件、配置、配对和版本备份在设备 `/opt/instrument/backups/stability-dev-20261013T012721Z`。

验收后 `finalize_board_runtime.py --apply` 在空闲/未配对/许可关/待传零条件下，恢复原config/pair语义，唯一配置差异为保留用户指定音量10；正式版本元数据从WSL包读取，使用已有S80启动，不再带模拟输入环境。前后记录写 `normal-runtime-restored.json`，不删除失败原片、待传或测试录像。已执行：正常主PID853、bootCAM-000123-0775cf1a，无模拟输入；相机及内核不变，空闲/未配对/许可关/待传零/volume及saved_volume均10。恢复前另备份 `/opt/instrument/backups/stability-final-20261013T045746Z`，内含旧installed-build。

回退需先核对serial/device和空闲、停止hello.application_pid对应主程序，从上述备份逐文件恢复旧程序和对应旧语音；回退配置音量仍应保留10，不覆盖Wi-Fi/相机/背光。旧installed-build来自最终恢复前的独立备份。恢复后正常S80启动、核对3.3.7/原SHA/无模拟输入和相机停止，再操作下一轮。不得批量按进程名杀进程或递归清理文件。

## 未验证与现场根因边界

- 昨天的故障设备CAM-41日志249次hello分7段boot、6次变化，但缺内核boot、PID、信号、退出原因；当前该设备未在线，不能从另一台CAM-000123的通过推断现场重启根因已查明。
- 用户确认电脑自带网口↔路由器LAN，但Windows Realtek报告MediaDisconnected/0bps/APIPA，普通进程重启网卡被拒绝。当前测试为USB→SSH Python中间层的真实UDP/HTTP双向链路；路由器有线/Wi-Fi直连未验收。Wi-Fi配置保持原样。
- 实际输出设备禁用、物理喇叭听感、异常供电冷启动可靠性未验证。音频不可用通过可控失败注入验证，不冒充实际停用设备。

`只读设备调查与验收入口.md` 是实施前历史快照；当前状态以本README、RUN_STATUS和带时间的运行证据为准。
