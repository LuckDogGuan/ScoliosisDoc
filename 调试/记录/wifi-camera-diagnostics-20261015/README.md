# Wi-Fi 摄像头修复与诊断验收（2026-10-15）

已部署上位机 **3.3.17**、下位机 **3.3.13**。上位机只保留 main 与主工作树入口。新程序已实际启动并通过原生画面诊断，随后已退出。全程未使用 ADB。

## 根因与修复

RKiPC 的 storage.mount_path=/userdata，使照片和录像写入 /userdata/video0；业务程序 VIDEO_DIR=/video0。旧日志持续出现 jpeg_timeout，三次录像开始/停止 RPC 成功后，取文件阶段报告失败；原目录实际保留了有效照片和 MP4。启动脚本现在固定 mount_path=/，统一输出到 /video0，并避免与业务 pending 目录跨文件系统 rename。

旧固件缺少 hardware_health 时，界面不再同时显示“不支持”和“检测中”。详细诊断按驱动、服务、RPC、文件及回传报告状态，8 秒必须返回明确结果。失败码、目录、RPC 返回、文件大小、HTTP 状态、时间和轮次可展开或复制；背景重试保留上次故障，旧轮次结果不得覆盖新轮次。服务、接口正常且收到可解码新画面才显示通过；驱动注册本身不是物理连接证明。

## 实板证据

目标 CAM-211ec7045815bf02，Wi-Fi 192.168.101.7，安装前已核对芯片序列号、应用 ID 和固定 SSH 指纹。

- 首次有效画面 568 ms；连续 30.252 秒收到并解码 30 帧。
- 五次正式控制器流程均完成收尾、上传与独立验收学生关联，录像时长分别为 5103、5355、6327、7647、9686 ms；逐帧解码、文件哈希与时长核验通过。
- 软件重启后，正常启动未加载模拟按键环境，mount_path 仍为 /，固件版本及程序哈希不变；10 秒收到 10 帧。
- 重启后额外一次录像 4661 ms，123 帧全部解码通过。
- 六次录像保留在上位机 build/wifi-camera-acceptance-20261015-* 独立目录；真实名单与学生记录未用于验收。三份旧失败录像仍在 /userdata/video0。
- 验收结束已恢复正常 GPIO 按键输入，并曾恢复原电脑身份的配对连接。随后原生应用退出，现有退出流程再次清除了配对；未擅自重新打开或重配。退出旧上位机会按既有逻辑解除配对，因此本次使用标准配对流程恢复；原 hostId 保持不变，事务号更新，非“配对文件全程逐字节不变”。

预览和拍摄使用真实板与 Wi-Fi，自动触发按键采用现有测试输入文件；物理按键手感、扬声器实际听感及断电冷启动未进行人工验收。原生窗口已启动并核对 3.3.17 文件版本。其实际业务日志进一步记录了版本 3.3.17+20261015、源码 f958776 和已解码新画面，结果为通过；未对关闭窗口的操作者作推断，也未将自动实板验收等同于人工按键验收。

对应记录：before.json、before-storage.json、before-camera-events.json（从轮转日志恢复）、native-app-acceptance.json、install.json、before-reboot-acceptance.jsonl、normal-startup-acceptance.jsonl、after-reboot-acceptance.jsonl、after-reboot.json、final-runtime.json、connection-restored.json。

## 软件验证与 Git

上位机全量 152 项测试通过；随后增加旧轮次忽略和重新检测轮次断言后，16 项定向测试通过；lib/test 与验收工具最终静态分析无问题。
下位机 ARM -Wall/-Wextra/-Werror 构建通过；传感器/服务/RPC/路径夹具、真实快照 RPC/照片等待/完整性/HTTP 拒绝、诊断租约、启动录像恢复、按键采样隔离、稳定性、事件扫描延迟和最短录像测试通过。

上位机源码 f9587766db7c280cbbdc4284c83aac08affc64f6；下位机源码 96528cabe077（完整来源见正式 BUILD.txt）。
Windows ZIP/安装器：ScoliosisFlutter/releases/windows-3.3.17-f958776；固件唯一正式包在 WSL /home/guanjx/luckfox/Scoliosis/releases/3.3.13。SHA256 与完整结果见 VALIDATION.json。

上位机已有工作先按诊断、工具、旧版归档提交，再快进合入 main，删除已合并功能分支。两个旧构建工作树的提交均已在主线；十个暂存发布文件逐 SHA256 相同，额外运行库也确认已保留在主目录或正式 ZIP 后清理。当前 Git 只登记一个工作树。第一个临时目录曾因权限问题无法删除最终空目录；组合清理命令被自动审批拦截，未换工具绕过，空目录可能仍在磁盘，但不再是 Git 入口。

GitNexus 编辑前风险：诊断工作进程 HIGH、上位机开始/结束测试 HIGH，已报告并限定范围。未改动所检查的 CRITICAL 公共 RPC/HTTP 处理器。下位机使用逐文件哈希核对的只读临时索引。新验收工具和二进制/归档不具备完整符号覆盖，另按实际 Git 路径清单、哈希、构建和实板结果核对。最终提交和 tag 见 COMMITS.json。未推送远端。

## 回退

板端安装器原文件备份：/opt/instrument/backups/bundle-20261015T084921Z-2037/rollback-files.tar。
相机原配置和原启动脚本：/opt/instrument/backups/wifi-camera-20261015T084906/。
回退前关闭拍摄许可，等待录像与上传结束，停止业务及相机服务；按安装映射恢复原程序与启动文件，不覆盖 capture、state/events、配对和 Wi-Fi 配置。恢复原 mount_path=/userdata 会重现此次路径错误，应用回退可保留已修正的 mount_path=/。
Windows 可使用旧完整版本目录回退；保留当前工作空间和数据库，不混用不同版本的 Release 文件。
