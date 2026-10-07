# 3.3.1 实施结果

目标板：41eda5f2c5b00de1 / CAM-41eda5f2c5b00de1。现已安装并运行3.3.1。

- 中键：熄灭、常亮、慢闪、快闪、3秒呼吸；背光：手动亮灭。
- 复用 Linux GPIO/PWM sysfs、flock、板端dtc/configfs；不改原三键业务和light_update。
- 默认30秒结束，INT/TERM/HUP与可处理错误执行关闭。高低有效可按实际模块校准。
- ARM与host构建、灯光回归、现有业务回归、Python真实SSH调用、身份拒绝检查通过。
- 实板五模式/超时/TERM/占用检查、安装→回退3.3.0→再安装3.3.1、软件重启检查通过。
- 配置与配对SHA256保持一致；现场Wi-Fi未连，本次SSH使用ADB转发，未宣称独立LAN验收。
- 接线由用户核对；未提供电流/电压数字。实体灯效、平滑度、电气测量、实际三键与冷断电验收仍需人工完成。

## 交付与追溯

正式完整包仅在 WSL：`/home/guanjx/luckfox/Scoliosis/releases/3.3.1/instrument-v3.3.1.tar.gz`；版本入口见 [发布索引](../../../releases/README.md)。
完整操作说明：[中键灯与背光说明](../../软件架构/中键灯与背光_3.3.1_说明.md)

- WSL正式目录：/home/guanjx/luckfox/Scoliosis/releases/3.3.1。
- 当前源码提交：1f45fd2167d94a69e280515ae3804300a679fa94。
- 发布归档提交：055534ee56d2e0be20ac21ae5775b0794f5a2542。
- 注释tag：instrument-v3.3.1，指向源码提交，注释记录归档提交及包SHA256。
- SHA256：8780eeec1541db89924eef45b03b3c019bf3672f9c8fda481ed9832c275ddc8b。
- Git提交/tag均在WSL本地，未推送。
- Windows文档/Python新增和修改保留为工作区改动，已有仪器测试工具等其他改动保留。

## 操作

~~~sh
/opt/instrument/bin/instrument_app --light-test center breathe --ground-verified
/opt/instrument/bin/instrument_app --light-test backlight on
~~~

前者需操作者已核验GPIO32低电平回路。实际连接与供电不要自行改动。
其他center模式：off / on / slow / fast；用 --seconds 3 可短测。
最后一个正式安装备份：/opt/instrument/backups/bundle-20261007T074025Z-1514。

## 证据

- [实板五灯态与退出](board-tests.json)
- [Python真实调用与拒绝记录](python-light.jsonl)
- [安装、回退、再安装](install-rollback-check.log)
- [软件重启](reboot-check.json)
- [最终完整包安装与源码对应](final-package-install.log)
- 版本整理和逐文件清理记录见 release-layout-cleanup.json / legacy-release-metadata.json。



2026-10-07 归档整理：正式固件包唯一放 WSL；源码快照核对后移除，提交及 SHA256 对应关系见 `../release-organization-20261007/README.md`。以上实板验收边界不因整理而改变。
