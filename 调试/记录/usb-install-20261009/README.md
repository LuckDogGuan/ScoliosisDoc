# USB 下位机安装记录 — 2026-10-09

用户授权按唯一当前连接烧录；同时连接两台时再询问。本轮唯一 USB 序列号为 `3253c006806f5194`，应用 ID 保持 `CAM-000123`。另一台历史目标未操作。

- 正式应用包来自 WSL `releases/3.3.7/instrument-v3.3.7.tar.gz`，外层与包内校验通过；3.3.0 → 3.3.7。本轮为应用包安装，未刷写原厂系统镜像。
- 停机前通过板上 localhost 的只读 UDP 状态核对：idle、拍摄许可关闭、无录像/上传/诊断/声音任务，active-v3为空，writing为空。保留已有配对。
- 已核对旧/新 RkLunch.sh 差异并安装包内启动脚本；新版加入北京时间和诊断 JPEG 设置。原相机配置仅变化 enable_jpeg=1、enable_cycle_snapshot=0、jpeg_qfactor=95、jpeg_buffer_size=4194304（以 after.json 记录实际差异），其余参数逐节核对。
- 安装记录与回退：`/opt/instrument/backups/bundle-20261009T075447Z-1626`，result为exit_code=0；安装后全部文件哈希通过。
- 电脑端首次 adb pull 目录失败，旧 adb exec-out 不支持；改用板端 tar 文件与英文临时路径导出成功。没有重复安装；原失败日志保留。完整本地回退审计为 rollback-audit.tar，可能含现场 Wi-Fi配置，仅本地留存，不提交 Git。
- 重启后核对序列号、版本3.3.7、程序 SHA256、全部安装文件哈希，instrument_app/rkipc存活及RPC socket存在；新boot_id、idle、gate=false、pending=0。config、pair及两份Wi-Fi配置哈希保持。
- 最终状态 Wi-Fi available，wlan0=192.168.101.3。音量沿用现场30，配对身份保持。

证据：operations.jsonl、installation.json、before.json、after.json、final-state.json、rollback-audit.tar。重启及服务检查不替代实体灯效、按键、实际相机帧与临床验收。

未修改下位机业务源码，未提交Git。工具与失败出口保留以便追溯；请勿直接重跑安装脚本。
