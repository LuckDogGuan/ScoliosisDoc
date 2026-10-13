# ADC 独立测试（2026-10-09）

结论：SARADC 驱动可读，但物理 Pin33/34 当前接线不能测电池电压。

- 图纸 Pin33：GPIO1_C4（GPIO52），没有 SARADC 功能；Pin34：GND。
- 本地 Luckfox-Pico-Zero.pdf：SARADC_IN0 = GPIO4_C0，SARADC_IN1 = GPIO4_C1；VCCIO2 标注 SARADC/PWM(1.8V only)，SARADC_IN0 必须上拉。
- 用户补充确认已有分压电路，采样线接 Pin33，地线接 Pin34；分压电阻值及 Pin33 实际电压未测。不要将这路 3.3V 直接移接 SARADC；需确认可接入的 ADC 测试点并分压，使 ADC 输入在 0～1.8V 内。
- GPIO 读取高/低不能替代模拟电压采样。

## 文件

源码唯一在 WSL2：/home/guanjx/luckfox/Scoliosis/tools/adc-test-20261009。

adc.original.c 为用户示例原样复制；adc_probe.c 为独立测试版，检查文件打开、解析及10位数值范围，读取10次后退出。原始示例在判空前调用 fseek，测试版改为先检查打开结果再读取。adc_probe 为 ARM 程序；adc_probe_host 为缺少 ADC 节点错误路径检查程序。主机检查返回1，未崩溃。

构建：

```sh
cd /home/guanjx/luckfox/Scoliosis/tools/adc-test-20261009
/home/guanjx/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc -std=c11 -Wall -Wextra -Werror -O2 adc_probe.c -o adc_probe
```

## 实板结果

USB序列号3253c006806f5194，型号Luckfox Pico Zero，应用ID CAM-000123。
IIO设备 ff3c0000.saradc，scale=1.757812500 mV/count。
公式：ADC引脚电压V = raw × scale / 1000。
10次读取：ADC0 raw=1023，1.798242V；ADC1 raw=353～357，0.620508～0.627539V。
ADC0满量程与原理图上拉说明一致，但没有实测电路验证；ADC1来源没有通过接线确认。两者不能视为Pin33上的电压或电池电量。
程序退出码0；全部CSV电压值已与公式核对。
原始记录：adc-samples.csv、result.json，后者包含身份、时间和程序SHA256。
实板文件仅在/tmp/adc-probe-20261009-3253c006806f5194，无开机启动，不修改应用。

复测（Windows，只读）：

```powershell
adb -s 3253c006806f5194 shell /tmp/adc-probe-20261009-3253c006806f5194
```

未验证电池百分比、分压校准、输入电压变化响应。后续先正确接入ADC并用万用表对照。
未提交Git，未制作升级包，现有业务源码不变。
官方ADC说明：https://wiki.luckfox.com/Luckfox-Pico-Plus-Mini/ADC/
