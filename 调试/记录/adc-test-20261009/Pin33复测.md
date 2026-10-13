# Pin33/34 实际接线复测

2026-10-09。用户补充照片并确认已有分压电路；不再将其描述为电池正极直接接入。照片不能确定电阻值及分压输出电压。

- 实际USB设备3253c006806f5194，Pico Zero，沿用已核对的同一设备。
- 物理Pin33对应GPIO52。读取前，内核pinmux显示MUX UNCLAIMED、GPIO UNCLAIMED。
- 独立脚本临时申请GPIO52，设置为输入，采样10次，绝不设置为输出；同步只读SARADC0/1。
- Pin33数字输入10次均为0（低电平）。这不是0V测量结果，也不能据此断言断线或分压错误。
- ADC0 raw=1023，ADC1 raw=353～357；scale=1.757812500mV/count。ADC0约1.798242V，ADC1约0.620508～0.627539V。它们没有映射到物理Pin33。
- 当前接法可以读取Pin33高低状态，但没有获得该引脚的模拟电压或电池电量。
- GPIO52临时导出已释放，内核再次显示GPIO/MUX UNCLAIMED；临时debugfs挂载已卸载。现有GPIO0/3/4和系统GPIO34/117/118未更改。

WSL脚本：/home/guanjx/luckfox/Scoliosis/tools/adc-test-20261009/pin33-input-test.sh。
实板临时脚本：/tmp/pin33-input-test-20261009.sh。
原始证据：pin33-samples.csv、pin33-result.json。

下一步若需诊断为什么为低电平，先用万用表实测Pin33相对Pin34的直流电压，记录两个分压电阻值；软件数字0无法反推模拟电压。
