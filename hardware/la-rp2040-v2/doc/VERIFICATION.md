# LA_RP2040 V2 验证记录

工具：KiCad 9.0.9（官方 `kicad/kicad:9.0` 容器），2026-11-12。报告原文见同目录 `erc_report.txt`、`drc_report.txt`。

## 已通过的检查

| 检查 | 结果 |
|---|---|
| 原理图网表 vs `gen/design.py`（`gen/check_netlist.py`） | 358 个管脚、79 个网络，0 处不一致 |
| ERC（`kicad-cli sch erc --severity-all`） | 0 错误，0 警告 |
| DRC（`kicad-cli pcb drc --schematic-parity --severity-all`） | 0 错误；0 个未连接项；原理图一致性 0 问题；1 条警告 |
| 器件 courtyard 重叠（`gen/check_place.py`） | 无 |
| 外壳与 PCB 占位模型的布尔干涉（`enclosure/enclosure.py`） | 上盖/底壳 0 mm³，外壳/PCB 0 mm³ |

DRC 规则：最小间距 0.15 mm、最小线宽 0.15 mm、过孔 0.55 / 0.3 mm、孔到孔 0.25 mm、铜到板边 0.3 mm。

剩余的 1 条警告是 `via_dangling`：U11 的 DIR 过孔只在背面有连接（三颗背面电平转换器共用 DIR567，网络从别处接入）。这个过孔多余但无害。

## 走线统计

| 层 | 走线长度 |
|---|---|
| F.Cu | 649 mm |
| In1.Cu（GND 层） | 422 mm |
| In2.Cu（3V3 铺铜 + 信号） | 579 mm |
| B.Cu | 589 mm |

过孔 285 个，全部为通孔。内层被信号线占用的情况见 README「PCB」一节的说明。

## 没有验证的内容

- 没有打样，没有任何实物测试：USB 枚举（包括 C-to-C）、官方 debugprobe 固件运行、各电压下的电平转换、SWD 速率、ADC 精度、ESD 等都未测。
- 没有做信号完整性、电源完整性或热仿真。
- 器件 3D 模型：USB-C 座和拨动开关在 KiCad 官方模型库里没有模型，板子 STEP 和渲染图里缺这两个器件；外壳是按封装图的外形尺寸建的占位模型，没有用厂家 3D 模型核对。
- BOM 里的保险丝、TVS、LED、晶振给的是规格和示例型号，没有核对供应商库存和价格。
- V1 板「Type-C 直连不枚举」的根因没有在实物上确认（见 README 的分析）。
