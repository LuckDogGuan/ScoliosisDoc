# Windows LAN 链路与下位机背光采样间隙只读调查

日期：2026-10-13。没有改变网络、驱动、电源、按键、配对、固件或板端服务，没有干扰正在执行的 gap probe。

## Windows 网口：确认没有物理链路，原因未确定

用户已确认拓扑为电脑自带网口连接路由器 LAN。本次只检查 ifIndex 31：Realtek PCIe GbE Family Controller（以太网 2）。

- 确认事实：AdminStatus Up，MediaConnectionState Disconnected，LinkSpeed 0bps；WMI NetEnabled False、NetConnectionStatus 7；统计收发字节均0。
- PnP：设备Status OK、CM_PROB_NONE，ConfigManagerErrorCode 0。Realtek签名驱动rt68cx21/rt68cx21x64.sys，版本1168.26.50.2025，日期2025-07-10，oem28.inf。
- 电源：CM_POWER_DATA最近期状态枚举1，对应D0。不能认定设备当前在D3休眠。Get-NetAdapterPowerManagement报“连到系统上的设备没有发挥作用”，未取得该接口的完整电源管理状态；这个查询错误也不能单独证明网卡坏了。
- 配置：速度双工为自动；EEE、环保节能、Power Saving Mode、Gigabit Lite开启，Advanced EEE关闭。这些是配置事实，没有故障对照实验，不能当作原因。
- 日志：过去7天System的rt68cx21事件0条；Kernel-PnP Configuration、Device Management、Driver Watchdog未检出此PCI实例事件。看到的WUDFRd错误属于其他ACPI/ROOT设备，Remote NDIS错误属于USB适配器，均不是本机Realtek网口证据。
- 证据边界：确认当前carrier未建立，尚不能区分线缆、路由器LAN端口、PHY、电源节能或协商异常。签名驱动/无PnP问题也不能证明链路硬件正常。Enable命令完成和AdminUp不等于物理链路恢复。

电源字段解释依据：[Microsoft CM_POWER_DATA](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-cm_power_data_s)、[DEVICE_POWER_STATE枚举](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ne-wdm-_device_power_state)。完整分类快照在windows-realtek-link-evidence.json。

## 背光：存在同步mux调用导致采样间隙的具体路径

- light_test.c:311只跳过亮度不变；0与100的每次实际切换都走:340 backlight_gpio_mux，不仅PWM回GPIO时调用。
- :299–301执行devmem读、写、读；:303–304通过run_command同步等待sh及子命令。相同GPIO模式下重复开关仍重复执行硬件mux恢复。
- buttons.c:27超过100ms采样间隔会清空stable/released并返回-1；持续按住不会自行恢复，必须再次取得全松开样本。backlight_tick:52也会disarm。
- 背光在500ms按住时开启，instrument_can_start在1500ms有效按住后才允许开录。因此，若背光开启时mux同步调用超过100ms，下一次采样可能变为无效，当前连续按住无法达到开录条件。runtime_v3.c:1196在主循环执行背光；:1203–1206记录slow_loop分段，可由实板日志验证。
- 既有host背光测试启用LIGHT_TEST_HOST，:292–293直接跳过mux；它们可证明手势边界，不能证明实板sh/devmem耗时。
- 本次新鲜运行test_buttons.c通过boot hold、抖动、交错按键、无效采样、gap后保持按住直到松开、计时溢出等断言，编译缓存在/tmp/buttons-gap-audit-ghefoois。

目前确认的是代码调用链和采样失效规则。尚未证明目标实板mux实际耗时超过100ms，亦未将当前第二轮录像失败归因为该路径；正在运行的实板gap/slow_loop证据由主线程采集。

源码身份与分类证据：backlight-gap-readonly-evidence.json。没有修改现有源码或测试。
