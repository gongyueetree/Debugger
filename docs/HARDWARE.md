# 硬件工程、可视化与引脚

工作台和左侧「工具汇总」均提供 CH347 Debugger 与 LA RP2040 的原始 KiCad 9 工程、可缩放原理图、PCB 正反面与交互式 3D 装配视图。启动本地 Agent 后也可离线查看，无需 CDN 或在线模型服务。

## 文件与来源

`dist/hardware/ch347/source/` 和 `dist/hardware/rp2040/source/` 保存用户提供 ZIP 内的 `.kicad_pcb`、`.kicad_sch`、`.kicad_pro`，文件内容未修改。每块板的工程 ZIP 仅打包这三个源文件，不包含工作站缓存。`manifest.json` 记录源文件和派生资源 SHA-256。

原理图和 PCB 预览由 KiCad 9.0.9 导出 SVG。PCB 背层 SVG 原文件为顶视透视图，网页镜像 X 轴后呈现翻板视角。GLB 来自同一 PCB 的 KiCad VRML 导出，再由 `scripts/vrml_to_glb.py` 转换，保留器件模型、颜色及原始正反面丝印。KiCad 标准器件模型来源、文件哈希及许可位于 `model-sources.json` 和 `KICAD-MODELS-LICENSE.md`。模型用于装配示意；器件选装状态以实际焊接为准。

工作台、工具卡片与接线页面均使用 KiCad 精确 CAD 渲染。另存的 `product-hero.png` 是 AI 概念展示图，未在界面使用，不能作为接线、丝印或生产参考。

3D 查看器包含自托管 Three.js 0.180.0（MIT）。默认使用 WebGL，缺少 WebGL 时使用 Canvas 2D 对同一 GLB 三角网格做深度缓冲渲染，仍可旋转、缩放和平移。兼容模式无 PBR 高光，显示外观可能与 KiCad 光线追踪略有差别。点击「正面丝印 / 背面丝印」可正视两面的管脚文字。

## 物理接口与丝印

两块板均为 35 × 16.5 mm、1.6 mm 厚。J2 为双面边缘 2×6 排针；奇数焊盘位于 F.Cu，偶数焊盘位于 B.Cu，同一对共享 XY。正面 USB 在左，J2 在右，1 在最上方；翻到背面后 USB 在右，J2 在左，2 在最上方。

| J2 | CH347 丝印 | CH347 网络 / 功能 | RP2040 丝印 | RP2040 网络 / 功能 |
| --- | --- | --- | --- | --- |
| 1 | TDO | TDO / MISO | GND | GND |
| 2 | 3.3V | 3.3 V 电源输出 | 3V3 | 3.3 V 电源输出 |
| 3 | TDI | TDI / MOSI / UART0 TX | CH0 | GP20 / SWCLK / D0 |
| 4 | CTS | CTS1 / GPIO6 | 5V0 | USB 5 V 电源 |
| 5 | TCK | TCK / SCK | CH1 | GP21 / SWDIO / D1 |
| 6 | RXD | UART1 RX | CH5 | GP25 / UART RX / D5 |
| 7 | TMS | TMS / SPI CS0 | CH2 | GP22 / nRESET / D2 |
| 8 | TXD | UART1 TX | CH6 | GP26 / ADC0 / D6 |
| 9 | TRST | nTRST / GPIO5 | CH3 | GP23 / D3 |
| 10 | SCL | I²C SCL / GPIO3 | CH7 | GP27 / ADC1 / D7 |
| 11 | GND | GND | CH4 | GP24 / UART TX / D4 |
| 12 | SDA | I²C SDA / UART0 RX | CH8 | GP28 / ADC2 |

RP2040 功能映射适用于本项目提供的板卡固件。CH6 是原始丝印，ADC0 是相应固件功能；界面同时显示两者，切换功能不覆盖丝印。串口 TX 接目标 RX、RX 接目标 TX。电源脚不自动高亮为信号，3.3 V 输出不是 VTref。

CH347 原生 SWD 与芯片版本和驱动相关。本工程只标注 JTAG 网络，尚未完成原生 SWD 物理接线核验，页面明确显示此限制，不推测 SWDIO / SWCLK；RP2040 DAP 的 SWD 映射已由本项目固件配置确定。软件测试不能替代硬件验收。

## 重建

正常运行无需 KiCad、Node 或 numpy。仅重建预览时需要完整安装 KiCad 9（包括 3D 插件和官方模型库）、Python numpy：

```bash
python scripts/build_hardware_assets.py --kicad-cli kicad-cli --models-dir /path/to/kicad-packages3D
cd scripts/viewer
npm ci
npm run build
```

如果原工程引用 KiCad 6/8 模型变量，构建脚本会将其指向指定的模型目录。不要用图像生成模型重画或修改丝印。若改变硬件引脚或丝印，请同步 `hardware-data.js`、固件配置与测试，并再次核对电气连接。

```bash
python -m unittest discover -s tests -v
node --test tests/test_waveform.js tests/test_hardware.js
```

参考：
- https://docs.kicad.org/9.0/en/cli/cli.html
- https://gitlab.com/kicad/libraries/kicad-packages3D/-/tree/9.0.0
- https://github.com/mrdoob/three.js/tree/r180
- https://openocd.org/doc/html/Debug-Adapter-Configuration.html
