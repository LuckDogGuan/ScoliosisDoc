# 当前实施状态 — 2026-10-13

最终业务源码已冻结。下位机 core 61870f3、installer eadccc3、正式归档 d6d67cc / instrument-v3.3.8；上位机业务 5165f96。下位机实板 SHA256 4a5841e12327bef0f6ea5fc8b75cc2bde29e3d5a21aa9f801fca289796753062，与正式包逐字节相同。正式包 SHA256 2b0b694bd894d39549de8bd8cc75daefec2107bd5559d5cec8460c173f62afa8。

最终音量10一小时测试从北京时间10:39:00左右计时，预计11:39后完成。执行会话31561；USB中间层16699；五分钟监控50809。最终数据 build/stability-board-20261013-volume10-final，日志 board-volume10-soak.log。monitor-5min.jsonl append保存所有检查；首次新监控在更换日志前读到旧主动中断日志，attention为启动过渡，不能称实板新故障。当前 RUN_STATUS 已标记最终测试。

上位机全量87项PASS、静态检查无问题；真实Windows系统静音/音量零/恢复16项通过，同一实例恢复通过；Windows原生GUI语音和approveClose进程退出PASS。下位机host/check-host及音频失败、独立采样/卡住采样失效/重建/关闭、事件扫描阻塞、Wi-Fi维护阻塞不拖启动语音、异常录像确认停止、进程组回收通过。

用户要求背光不改，所有light_test.c修改已撤回，最终源文件与3.3.7一致。音量10已真实协议确认current/saved=10，后续恢复配置必须保留用户的新值10。

真实复现：旧语音停止不返回；无音频阻止下位机开录；完成事件主循环扫描>100ms导致有效按住变无效；背光同步调用耗时也会使主循环过100ms，但不改背光，用独立采样隔离。启动声音曾与Wi-Fi维护共享队列，阻塞注入重现后已隔离。原CAM-41昨天6次boot变化仍缺内核/PID/退出证据，根因不能认定。

早期usb1名单T1/T10排序夹具问题；usb2/gap实板采样失败；sampling连续47轮，由agent按用户音量10要求主动暂停；volume10预冻结17轮，为修启动语音主动暂停。均未完成一小时，不计完整PASS。最终完整验收只认volume10-final的passed行与实际elapsed>=3600000。

电脑Realtek以太网2已核对用户物理接线声明，但当前MediaDisconnected/0bps/APIPA，普通账号Restart-NetAdapter拒绝访问；目前真实UDP/HTTP双向测试通过显式serial/device的USB→SSH Python中间层，不能称路由器直连已验收。Wi-Fi配置未更改。真实输出设备禁用、物理喇叭听感、异常供电冷启动未验证。

待完成：一小时实板及五分钟记录，额外真实静音拍摄与必要故障注入；Windows归档/索引提交（完整87文件zip已生成SHA f1a45848287a5f618197ea321ac75851760446fa052e1feaf5f4e78e1cc39733）；设备恢复原pair/config（volume=10）、正式版本元数据、原正常启动不带INSTRUMENT_BUTTON_FILE；正式包只WSL。工具和记录分开提交，保留既有ADC/烧录未跟踪工作。原设备备份 /opt/instrument/backups/stability-dev-20261013T012721Z，原app SHA33cb2d4fc887948097ef4878589dad52aaa8158390c187c0b397315caaddfe01。最终验收完成后暂停heartbeat automationId5。

## 12:15 最终故障与真实静音复验启动

之前音量10一小时181轮、elapsed3609422ms已通过（FW3.3.8/App3.3.6）。追加真实Windows静音注入已通过5种故障；60秒设备完成实际60001ms暴露测试及查询回补上限过严，已修为65000ms并保留原始时长，上位机3.3.8源eff9611、87项PASS/静态检查无问题。下位机3.3.9源9a5af83，归档e2a5ee6，实板e4466b57a3349e83ff4744cac1e02c41a010be82482aff1f3f46ad09e7fe3849。

最终故障脚本开始于12:15:30，独立faults-final目录，实际系统静音；自动按键、丢开录事件、丢完成响应、双向断线、慢上传、半包、60秒、SIGKILL重启、至少20轮并一小时；恢复系统声音后同一播报实例再拍3轮。monitor-5min-final.jsonl每300秒检查设备、原始/解码时长、归属、哈希、许可和系统静音。首条使用不存在evidence.jsonl路径只记录启动状态，立即更正stability-evidence.jsonl，12:16检查无异常。

## 12:21 USB调试传输隔离后复验

12:15轮完成第1段后许可过期，后续prepared超时：同一SSH传输包含旧待传60秒视频与控制，控制响应从0.7s升至3.5s，实际租期6276ms触发正确暂停；非静音直接证据。保留board-faults-shared-ssh-boundary.log/windows-muted-board-shared-ssh.json，不能计PASS。调试工具已增加独立且同host-key固定的控制SSH连接，视频用原连接，记录control_elapsed_ms；协议/许可不改。12:21开始新的faults-isolated目录一小时复验，monitor-5min-isolated.jsonl。Windows3.3.8完整87文件包SHAa23f572a3db992c219f150c341a31b3d5e402c6cc5dc6b2bcc1c774521f470cb，编译47.2s、native/zip逐文件读回校验通过。

## 12:25 实板SIGKILL暴露HTTP先到时序问题

前6种故障通过；60秒实际60001ms，完整解码60017ms/1753帧/29220893字节。SIGKILL旧主PID3623，新PID1272/bootCAM-000123-d9f36571，kernel不变、RKiPC439不变，确认相机0，原始录像/video0/20261013122458.mp4仍在SHA18b9029c94a7b911d5324e9d62755b098517ca3e7d1191ee2313e91e01692a4b。失败结果归原人员正确，但HTTP失败通知先于新hello触发旧许可下自动prepare；失败分支manual_stop使继续提示未及时设定。测试明确失败，不能计一小时PASS。

定向回归先重现resumeRequired false（RED），修复完成HTTP检测boot变化先停旧许可，并将自动prepare失败标记prepare_failed；GREEN2项通过。上位机3.3.9全量测试进行中，下位机不需再改。

## 12:33 3.3.9最终实板一小时启动

上位机源ae13512，新增HTTP-before-hello回归GREEN；全量单worker87项PASS，analyze无问题。下位机正式3.3.9包与实板26文件逐字节SHA核对通过（formal-board-payload-preflight.json）；启动和相机适配文件与已安装一致，不需改背光或重启相机。Windows3.3.9 release编译开始。

最终运行faults-verified独立目录，真实Windows mute=true；计时约12:33:50开始，至少20轮且实际>=3600000ms，最后同一SapiSpeaker恢复系统声音再拍3段。monitor-5min-verified.jsonl每300秒只读校验。之前faults-isolated的6段及SIGKILL证据留存于board-faults-http-restart-boundary.log/windows-muted-board-http-restart.json，不能当最终一小时PASS。

## 12:39 最终7种实板故障全部通过，继续一小时

60秒实际60002ms，完整解码59983ms/1753帧；SIGKILL1272→2335，bootd9f36571→39ea0692，kernel及RKiPC439不变，/video0/20261013123759.mp4保留SHAff1436c815a197366e968941df2c4a592d7d5d9cbfa634439900c217fb51d27f，相机0已确认。上位机继续提示正确，操作确认后stability-7原人员重拍成功，未错误切人/自动恢复许可。首个5分钟检查7段/no issues/volume10/muteTrue/pending0。Windows3.3.9正式归档2cccca5，源ae13512，完整87文件，ZIPSHA3ad0f9698aad4cf64ebd3d3f462604a0461a8a134ab29d21b64c4e166e0670bc。最终一小时仍在进行。

## 用户改为20分钟，最终停止与恢复

用户“验证20分钟就算了”取代最终一小时要求。gate_disable主动停止于12:55:23，最后收尾完整57段、actual1291609ms；7种故障均通过，收视频98,090,626字节全部SHA读回、全帧解码、最大时长差34ms。accepted-20minute-validation.json单独标记按用户条件验收；原60min脚本下一prepared因agent关闭许可而超时，exit1日志真实保留，不伪造passed、不当现场故障。未再跑该轮的最终一小时/恢复声音3段；此前真实Windows同一speaker恢复音频状态测试已通过。

Windows端点恢复该轮起始状态muteTrue/volume0.100031；设备音量10。finalize执行正式26文件SHA匹配，原config/pair恢复且volume唯一差异10，installed-version/build为正式3.3.9；正常S80启动，PID853/boot0775cf1a、kernel原值/RKiPC439不变、无INSTRUMENT_BUTTON_FILE、idle/gatefalse/unpaired/pending0/camera_faultfalse/audio_busyfalse。恢复前备份stability-final-20261013T045746Z。五分钟监控已停止；保留每次检查及原始失败视频，不清理录像。

最终独立RPC读回camera recording=0，installed-version及运行版本均3.3.9；用户测试模拟文件仅明确删除/tmp/stability-buttons-20261013一个自建路径，原buttons.sim保留。USB中间层单进程5376及自建ADB tcp22023转发已关闭，五分钟heartbeat5暂停。未删除任何录像或修改网络/背光。
