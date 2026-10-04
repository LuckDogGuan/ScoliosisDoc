# Git 更新与待办核对记录

日期：2026-10-04。按用户要求更新 Git、保存记录，并逐项核对 `调试/todo/待办.md`。

## 提交范围

下位机的 Git 写入在 WSL `Luckfox-Ubuntu-22.04:/home/guanjx/luckfox/Scoliosis` 执行。

- 提交：`19bba16` — `deploy: default MinMax Wi-Fi and volume 20 with persistent SSH update bundle`。
- 标签：`instrument-v3.3.0-20261004-minmax-volume20`。
- 包含默认配置、默认 Wi-Fi 模板、安装／打包脚本、GPIO 安装依赖、包验证脚本、CHANGELOG，以及最终不可覆盖的 image 和 bundle2 归档。
- 不包含 USB/UVC 试验工程、中间包、临时自检夹具或其他未提交工作。

Windows Luckfox 仓库提交待办、Wi-Fi 网络名称／密码文档、单文件教程、本次升级脚本、部署前后证据、最终包及板端回滚备份。Flutter 本次只读核对，无代码变更，不创建空提交。两个仓库均未推送远端。

版本包中的 BUILD/source_base_commit 是构建前基线；最终源码与发布归档由上述提交／标签关联。旧归档保持不变，没有覆盖已有发布目录。

## 核对结果

| 原待办 | 本次状态 | 仍需处理 |
| --- | --- | --- |
| 1. 下位机升级 | 部分完成 | ADB／独立 SSH 已验收；A/B 自动回退与 Flutter 上传仍待实现 |
| 2. 工作空间 | 已实现，待现场验收 | 中文目录切换、重启、空间隔离及用户备份恢复 |
| 3. 视频算法／曲线 | 部分完成 | 目前固定尺子图演练；真实视频帧推理与准确性验收 |
| 4. 按键／电池 ADC | 部分完成 | 新板实体按键验收；电池电路、ADC、校准与上报 |
| 5. 按键状态联动 | 设计／核心代码完成 | 当前新板完整按键／录像／提示音现场验收 |
| 6. 下一位姓名播报 | 已实现，待实测 | 实际 Windows Debug／Release 语音会话与喇叭听感 |
| 7. 数据导出 | 名单已实现，记录导出未完成 | 拍摄／角度／曲线数据格式、实现与一致性验收 |
| 8. 低功耗 | 未完成 | 功耗基线、策略和实际续航测量 |
| 9. 仪器分类命名 | 唯一身份已完成 | 用户可编辑名称／分类／分组及持久化 |

未把工作空间切换误判为缺少重启：当前 `main.dart::_switchWorkspace` 实际会启动等待旧 PID 的新进程。未把测试尺子图推理当作真实视频识别；未把名单导出当作拍摄数据导出；未以旧板录像验收替代当前传感器未识别的新板。

## 提交前检查

- WSL 使用既有 Windows GitNexus 缓存和 `scripts/gitnexus_wsl_review.mjs`，Git 读取代理到真实 WSL 仓库，执行 staged detect_changes：33 个文本变更文件、0 个映射符号／流程、risk=low。结果保存为 `gitnexus-firmware-precommit.json`；新增脚本未在旧索引中，符号计数不表示所有新代码已经图分析。
- Windows 同样调用 staged detect_changes；工具没有映射出变更符号，结合真实 staged 文件列表和 diff 核对提交范围。
- WSL staged diff --check 通过；Windows 文本统一换行并去掉末尾空行，不改日志字段、命令或测量值，随后检查。
- 已有 ARM/uClibc 编译、配置校验、包完整性与损坏包拒绝测试，以及独立 SSH 更新／重启证据。本次主要整理文档与提交，没有再次升级设备。
- 保留 `.gitignore` 和仪器 USB 测试工具等其他工作区改动，未一并提交。

待办详见 [待办与完成状态](../../todo/待办.md)；实机证据和回滚步骤见 [部署验收](部署与独立SSH升级验收.md)。
