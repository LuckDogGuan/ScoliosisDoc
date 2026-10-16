# 下位机 3.3.14 烧录与语音、拍摄回归（2026-10-16）

目标 CAM-211ec7045815bf02；USB 烧录，Wi-Fi 192.168.101.7 进行业务测试。
已运行 3.3.14，构建 dff5e1e54e94。源码 dff5e1e54e9478f059f2c33bf9f22710216a0b6c，
归档 242eee0，tag instrument-v3.3.14，语音修复 46ec53f。
正式包唯一位于 WSL /home/guanjx/luckfox/Scoliosis/releases/3.3.14，未复制到 Windows 仓库。

## 已通过

- 唯一 USB 板身份、包内版本、外层和内部哈希、空闲门禁、回退备份及安装文件校验通过。
- 软件重启后内核 boot_id 改变；运行版本／构建符合包，RKiPC 和 RPC 套接字正常。
- 实际 aplay 命令包含 boot_ready.wav、wifi_connected.wav；启动轮次两次播放完成均为 success。
- 真实 Wi-Fi 断开与恢复，采集到 wifi_disconnected.wav、wifi_restored.wav，各一次成功完成。
  恢复后多次检测没有重复播报；提前安排恢复任务，没有修改网络凭据。
- 首张可解码新画面 566 ms；连续 30.065 秒收到并解码 30 帧，详细诊断通过，目录均为 /video0。
- 五次录像时长 4841、5192、6539、7968、9852 ms；收尾、上传、匿名测试学生关联及全片解码通过。
  解码帧数分别为 128、137、174、209、263。
- 正常 GPIO 输入已恢复，进程不再带 INSTRUMENT_BUTTON_FILE；最终 idle、许可关闭、Wi-Fi available、音量 20。
  writing 为空，没有待上传 MP4；原有三份失败 JSON 元数据及 /userdata/video0 的三份旧失败录像保留。
- 配置和 Wi-Fi 文件最终哈希与安装前一致。正常输入恢复后 RTSP 可读取；
  RTP 标记计数不等于完整解码，解码证据使用上述五份 MP4。

## 配对及验收边界

安装器核验安装前后配对文件逐字节相同。测试中断的间隔后，板端实测无配对，
且原生上位机 3.3.17 窗口正在运行；不推断这一变化的操作者。
本轮使用独立身份 voice-acceptance-20261016、独立数据、18080 接收端口，
按标准流程临时配对，结束后解除该测试配对，最终保持未配对。
正常配对流程会改变事务和接收地址，不能把安装时的逐字节保持扩展为整轮测试都保持。
现有原生窗口未关闭、未操作，真实学生记录未用于测试。

实板、相机和 Wi-Fi 均真实，自动拍摄手势采用既有输入文件模式，结束后已移除。
扬声器实际听感、人工物理按键手感及断电冷启动未验收；播放返回成功不等于现场听感确认。
控制器夹具的 PC 版本显示 development，不冒充原生 EXE GUI 验收。

## 分类记录

| 类别 | 文件 |
|---|---|
| 烧录前后／版本 | before.json、after-install.json、release.json、install-cli.txt |
| 启动播报 | startup-events.json、final-runtime.json 中的 aplay_monitor 和 prompt_complete |
| 断网恢复播报 | network-recovery.json |
| 预览及五次拍摄 | camera-acceptance.jsonl、camera-fixture.json |
| 正常输入恢复 | final-runtime.json、normal-runtime-rtsp.txt |
| 验收汇总 | VALIDATION.json |

首次辅助网络监控文件未生成，未将该轮记为提示音通过；核验监控与恢复任务文件后补测通过。
原有失败元数据不属于本轮待上传录像，因此未为追求目录清空而删除。
验收录像保留在 ScoliosisFlutter/build/wifi-camera-acceptance-20261016-voice。
完整私有烧录／回退审计保存在 release.json 指向的 install_report，不复制配置或备份归档到 Git。

## 软件与 Git

4 项主机语音回归、ARM -Wall/-Wextra/-Werror 构建及包校验通过。
版本宏 GitNexus upstream impact LOW；版本／归档提交前 detect_changes LOW。
二进制归档无完整符号覆盖，另外核对实际暂存的四个发布文件、包内版本和哈希。
上位机源码未修改，仅在忽略的 build 目录生成带独立端口及配对清理的验收夹具，哈希见 camera-fixture.json。
本轮沿用已有分支，未增加分支或工作树；Windows 只提交分类文档和脱敏证据，不混入原有未提交目录。未推送。

## 回退

板端备份：/opt/instrument/backups/bundle-20261016T013249Z-2157/rollback-files.tar。
本地完整审计目录见 release.json 的 install_report；按其中安装映射和哈希恢复。
回退前关闭许可、等待录像／上传／诊断／声音结束，停止 instrument_app 和 rkipc；
仅恢复备份中的程序、声音和启动文件，不覆盖 capture、业务状态、配对或 Wi-Fi。
保留 mount_path=/ 的相机路径修复，恢复后重启核对版本、服务及新画面。
