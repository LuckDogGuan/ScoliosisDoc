# Wi-Fi 配对与状态语音改造：Flutter 先行实施说明

日期：2026-09-30。对应计划：[WiFi配对与状态语音改造计划_2026-09-30.md](WiFi配对与状态语音改造计划_2026-09-30.md)。

本次只修改 `D:\code\Scoliosis\ScoliosisFlutter`，未修改、编译或部署下位机程序和 WAV。实体按键尚未到货，不能把本次改动当作新配对、按键录像或板端语音的实板验收。

## 本次完成

| 项目 | Flutter 代码 | 当前行为 |
| --- | --- | --- |
| 定向在线查询 | `lib/net/device_query.dart`、`lib/app/app_controller.dart` | 电脑每约 2 秒向已知 IP 的当前/已配对或本轮发现的仪器发只读 UDP 查询。每次等约 1 秒；已证实支持查询的仪器首问漏答后最多补问三次。只接受同一来源 IP/端口、设备号、序号和随机数的回复。四次均漏答才记通信离线，配对记录不删除；有效回复清零漏答。 |
| 旧板兼容 | `lib/survey/survey.dart` | 旧板不回复新查询时，仍由原 `/api/v1/hello` 与原拍摄/上传通路工作。只有收到有效 V3 查询回复才切换该设备的在线判定；查询模式不再用 `holdOnline` 掩盖漏答。新旧补传调度没有并行新增。 |
| 状态与指标 | `lib/device/device_book.dart` | `host_id` 由本机随机生成，并随现有设备状态保存；有效回复记录设备阶段和 Wi-Fi 状态。只有 `snapshot_age_ms` 在 0–10000 且指标结构有效时更新指标，否则将指标显示为未知，避免旧值冒充实时值。 |
| 页面文字 | `lib/ui/pages/device_page.dart`、`lib/ui/pages/capture_page.dart` | “当前连接”改为“当前仪器”；解除配对与 Wi-Fi 断开分开表述；“在线”不直接写成“可拍摄”；拍摄页未就绪提示不再断言网络已断开。查询补问、通信离线和已配对分别呈现。 |
| 回归测试 | `test/device_query_test.dart`、`test/device_page_volume_test.dart` | 本机 UDP 假仪器检验错随机数/错设备号、有效回复、四次漏答保留配对、恢复和旧板无回复兼容；页面断言同步更新。 |

### 已编码的只读查询报文（待与板端联调确认）

电脑发往仪器 UDP 37020：`{"version":3,"op":"hello_query","device_id":"...","host_id":"...","sequence":7,"nonce":"16字节随机十六进制"}`。仪器需从同一端口回复 `version=3, op=hello_reply, device_id, sequence, nonce`，并可带 `wifi_state`（`recovering` / `needs_attention` 等）、`phase`、`snapshot_age_ms`、`metrics`。`metrics` 使用现有 `ssid/rssi_dbm/storage_free_mb/storage_total_mb/memory_available_mb/memory_total_mb/pending_count/battery` 字段。普通发现和查询回复仅用于状态观察，**不提供配对或上传授权**。板端未实现前，这条查询不会产生有效回复。

## TODO：下位机与按键到位后

1. **查询联调**：板端实现上述只读回复；核对版本、字段、长度限制、设备号、来源和重复包；在录制/上传期间也能及时回复。实板验证 2 秒正常查询、约第 1/2/3 秒补问、四次漏答、晚到旧包、换 IP、断网恢复及指标采样时间。根据实测统一最终协议字段。
2. **配对事务与安全**：中+左 3 秒开 60 秒窗口；电脑端增“配对中 → 仪器确认 → 持久保存”事务，事件号幂等、超时失败、旧配对迁移和控制消息身份校验。当前旧协议 `AppController.pair()` 仍先写配对并下发 `pair_event_id`，**不能称为新事务已完成**；新板切换前必须替换该路径。中+右离线解除及恢复同步也待板端实现与联调。
3. **上传许可**：待板端提供 `capture_id/size/hash` 待传清单和只按许可上传的能力后，电脑逐文件发许可、核对回执与断线重试。当前旧板仍自行补传；Flutter 没有启用第二套自动补传调度。
4. **实体键拍摄**：左+右 1.5 秒、开始语音后开录、松手停录、60 秒上限、低于 100 MB 拒录、短片留片；板端和 Python 调试入口都待实现。**电脑“开始拍摄”按钮暂留作旧板回退入口**；实板验收后再撤掉。现有固定 10 秒录制显示仍属于旧流程。
5. **语音与 Wi-Fi**：板端区分 Wi-Fi 恢复、电脑通信、配对和拍摄事件，按状态边沿及事件号去重；核对实际 WAV 内容和喇叭效果。电脑只显示从有效回复得到的 Wi-Fi 状态，电脑查询失败不得触发板端 Wi-Fi 断开重连。

## 验证与回滚

- `dart analyze` 对本次涉及的 Dart 文件：`No issues found`。
- `flutter test` 定向运行 `device_query_test.dart`、`device_page_volume_test.dart`、`device_repair_test.dart`、`capture_parallel_test.dart`、`survey_test.dart`：`All tests passed`。
- 当前证据只覆盖本机模拟与静态检查。未做新版协议的实板响应、按键、语音或 Windows Release 现场测试。
- 回滚新查询可停用 `AppController` 的 `_queryTimer` 调度，旧板 `/api/v1/hello` 与现有接收端仍在；设备及视频记录无需删除。切换完整新协议前保留旧版本和待传文件。
