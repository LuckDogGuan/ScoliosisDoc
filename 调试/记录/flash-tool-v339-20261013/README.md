# 一键烧录3.3.9兼容修复与实板验收

2026-10-13，已修复Windows工具并用最终EXE烧录当前唯一仪器。设备为41eda5f2c5b00de1 / CAM-41eda5f2c5b00de1，与上一轮CAM-000123不同，烧录前重新核对身份。

## 已修复

1. read_package变量digest在安装文件循环中覆盖了整体包哈希，导致传输校验永远错误。改用独立package_hash，实包回归先RED后GREEN。
2. 3.3.9的sounds/stability-voice-manifest.json只保存在包内，安装器只复制sounds/*.wav；工具错误要求设备存在该JSON，现与安装器对齐。22个WAV、启动提示均核对，JSON包内校验仍保留。
3. 首轮EXE安装PASS，重启后启动播报audio_busy=true触发严格门禁失败，startup-audio-red.json保留现场。仅post-reboot启用15秒音频等待；普通安装前、拍摄/许可/上传/诊断/配对窗口及未完成文件门禁不放宽，回归覆盖超时和忙碌拒绝。

GitNexus修改前影响：read_package LOW/4直接入口；idle HIGH/3直接入口、3流程，已修改前告知并重点回归；verify/flash_install LOW。未修改WSL固件源码或正式3.3.9归档，不改变背光/网络/音量配置。

## 最终结果

- 9项测试PASS，含自动Tk选包3.3.9版本显示；包损坏和目标不符拒绝。
- 最终EXE真实--install --force，installation/verification均PASS，进程退出0。
- 固件3.3.9，程序SHA与正式包一致，内核软件重启及业务新boot确认，相机进程和RPC socket正常，phase=idle，camera_fault=false，audio_busy=false，许可关闭。
- config、pair及实际Wi-Fi配置字节哈希保留；原设备音量30未额外改变。视频与待传未删除。
- EXE SHA `342a5628fade9aefd0f47cd17fd109f465b064953d9b6243ee4d92e0bb52f80c`；固件包SHA `3fc21b58f64a8abb8f08eb59ded5e140e22521a12f4da37bb3f63608f9c41aaf`。
- 最新回退 `/opt/instrument/backups/bundle-20261013T072818Z-3187`，本机回退tar导出SHA `f7af1b249e2e2d8cbe9abec37a6847352c60af7b30d92075aa086f86bf8324b6`。首轮升级前3.3.5回退仍保留 `/opt/instrument/backups/bundle-20261013T072102Z-2649`。

第一次安装后的音频误判与最终成功分开记录，未把第一次称为完整PASS。原始操作日志/回退可能含现场网络配置，只保留在本机 `D:\code\Scoliosis\Luckfox\调试\工具\一键烧录\release\记录\20261013-152805-41eda5f2c5b00de1-fe9409`，不提交；delivery.json仅保留安全字段。

## 使用

新版工具：[下位机一键烧录.exe](../../工具/一键烧录/release/下位机一键烧录.exe)。固件正式包仍只在WSL `/home/guanjx/luckfox/Scoliosis/releases/3.3.9/instrument-v3.3.9.tar.gz`。首次GUI选包后确认版本3.3.9，再开始；相同版本且文件一致将只校验。

本次验证安装/重启/文件与配置保留，没有重复长时间拍摄、物理喇叭听感或异常供电冷启动；这些不冒充已验收。
