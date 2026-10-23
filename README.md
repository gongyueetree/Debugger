# Debug Studio · CH347 + RP2040

面向 CH347T 四模式硬件与 LA_RP2040 板卡的 Web 下载、调试和测量工作台。包含可独立打开的前端、本机 Python Agent、真实工具后端、演示模式和可选 eve AI 任务助手。

**交付状态：v0.2 开发版。软件测试与三份 RP2040 UF2 交叉编译已完成，没有连接 CH347 / RP2040 实物进行验收。** 所有真实执行路径都会根据工具退出码、API 返回值和响应长度判定结果，无法连接或缺少依赖时返回错误；不会用演示数据填充真实结果。

## 立即启动

需要 Python 3.10 或更新版本。普通下载、调试和规则助手不需要 Node.js 或模型密钥。

```bash
git clone https://github.com/gongyueetree/Debugger.git
cd Debugger
bash start.sh
```

也可在 GitHub 选择 Code → Download ZIP，解压后按下面的方法启动。

- Windows：解压后双击 `start-windows.bat`。
- macOS / Linux：进入解压目录，执行 `bash start.sh`。
- 首次启动创建 `.venv` 并联网安装 `requirements.txt`。依赖安装失败后，可手动重试 `.venv/bin/python -m pip install -r requirements.txt`（Windows 为 `.venv\Scripts\python.exe`）。
- 自动打开 `http://127.0.0.1:8765` 并通过 URL fragment 完成本次配对，随后清除 fragment。每次服务重启都会生成新配对码。
- 如未自动打开网页，复制终端中的本地地址，点击“连接调试器”并填入本次配对码。
- 在线工作台也能连接此服务；若浏览器限制 HTTPS 页面访问本机 HTTP，直接使用本地网页。不要关闭浏览器安全保护。

仅体验页面、不安装硬件依赖：`python -m bridge.server`。网页默认显示明确标记的演示模式。

启动选项：`python -m bridge.server --port 8765 --no-browser --allow-origin https://your-workbench.example`。来源必须是无路径的精确 origin。

## RP2040 新增功能

- **MCU 调试 + 串口**：专用 CMSIS-DAP v2 固件，复用网页的 OpenOCD / GDB / UART 工具。
- **8 通道逻辑分析仪**：GP20–GP27，最高配置 20 MSa/s，最多 100000 点，边沿/电平触发、波形缩放、游标、CSV/VCD/PulseView .sr 导出。
- **ADC 数字示波器**：GP26/27/28 中选择一路，最高 500 kSa/s、最多 32768 点，12 bit 原始码、Vpp/RMS、游标、CSV 导出。
- **三份板级 UF2**：在「RP2040 固件」页下载，经 BOOTSEL 切换；三个配置不同时运行。完整对应固件源码和许可证一并提供。

输入没有模拟前端或电平转换：信号限定 3.3 V；ADC 输入 0–3.3 V 且不得超过实测参考电压。示波器当前是未校准的单次 ADC 采集，不具备通用示波器的宽输入量程、持续流或硬件模拟触发。详细接线、构建和实板验收见 [docs/RP2040.md](docs/RP2040.md)。RP2040 的 debugprobe 固件不支持 JTAG / SWO，openFPGALoader 继续使用 CH347。

## CH347 功能与要求

| 功能 | 本机后端 | 模式 | 实现范围 |
|---|---|---|---|
| FPGA 扫描、SRAM、配置 Flash | openFPGALoader `ch347_jtag` | 3 | 扫描、文件上传、执行计划、下载日志；实际 FPGA/文件格式以工具支持为准 |
| MCU 烧录与调试 | OpenOCD `ch347` | 3 | STM32F1/F4、RP2040、nRF52、ESP32 配置入口；暂停/继续/单步/复位、寄存器与内存读取、ELF/HEX 烧录；不是全系列兼容承诺 |
| GDB 接入 | OpenOCD | 3 | 本机 `127.0.0.1:3333`；可接 GDB/IDE |
| 串口 | pyserial / HID UART | 0/1/2/3 | 8N1，持续收发、文本与日志；模式 0 可打开两个系统端口；无 UART bootloader 自动下载协议 |
| SPI Flash | flashrom `ch347_spi` | 1 | 识别、备份下载、写入默认校验、独立校验、擦除 |
| I²C | WCH SDK / HID | 1/2 | 100 kHz ACK 扫描、7 bit 地址、1/2 byte 寄存器地址、读写；HID 单事务读 ≤63、寄存器地址与写数据合计 ≤62 bytes |
| SPI 原始事务 | WCH SDK / HID | 1/2 | mode 0–3、MSB first、SCS0、全双工；最多 4096 bytes；选取不高于请求的分频 |
| GPIO | WCH SDK | 3 | GPIO3/5/6 读电平、配置输出；与正在运行的调试/XVC 会话互斥 |
| SVF | OpenOCD | 3 | 单 TAP 链的 SVF 执行，需要 IR 长度与 IDCODE；未实现 BSDL 自动互连测试生成 |
| XVC（实验） | 自带 `bridge.xvc` / pyusb | 3 | 独立 CH347T USB JTAG bitbang，XVC v1.0 getinfo/settck/shift，本机 2542 端口；尚未进行 Vivado/ILA 真机验证 |
| 任务助手 | 本地规则 / 可选 eve | 全部 | 引导工作流，AI 可读取状态和准备计划，不能直接写硬件 |

CH347T 的 PID：模式 0 `55DA`、模式 1 `55DB`、模式 2 `55DC`、模式 3 `55DD`，VID 为 `1A86`。软件模式选择只用于准备任务，实际模式按设备枚举校验。每个系列仅允许连接一个设备，但可同时连接一个 CH347T 与一个 RP2040 并在页面选择；CH347F 的 PID/接口布局未纳入支持。

## 外部工具与驱动

本包不附带厂商 DLL、内核驱动、openFPGALoader、OpenOCD 或 flashrom 的可执行文件。请从各项目/厂商安装适合系统架构的版本，并放入 PATH。

- **openFPGALoader**：`openFPGALoader --list-cables` 应包含 `ch347_jtag`。先运行网页里的 JTAG 扫描。底层使用 libusb；Windows 应按工具文档配置正确的 JTAG USB interface，避免替换 UART interface 的驱动。
- **OpenOCD**：CH347 需要真正包含 `ch347` adapter 的构建；RP2040 使用 `cmsis-dap` bulk adapter；系统发行版的旧版本可能没有。目标脚本需要在它的 scripts 搜索路径中。
- **flashrom**：需要编译进 `ch347_spi` programmer。mode 2 HID 不通过这个 programmer 操作。
- **普通 UART**：安装 WCH 对应串口驱动，使系统枚举 COM / tty 设备。
- **pyusb / XVC**：pyusb 还需要系统 libusb。Linux 按上游文档配置 USB udev 权限；macOS 可用系统包管理器安装 libusb；Windows 需要兼容的 libusb 后端库与接口驱动。
- **HID mode 2**：Python 依赖包含 hidapi 与 ch347api。Linux 需对应 hidraw 权限。macOS 的 HID interface_number 行为没有实物验证；找不到设备时报告失败，不能宣称已跨平台验证。
- **WCH SDK**：用于 mode 1 I²C/SPI 和 mode 3 GPIO。Windows DLL 与 Python 位数必须一致；Linux `.so` 与 CPU 架构必须匹配，并按 WCH 官方说明安装 `/dev/ch34x_pis*` 驱动。

WCH SDK 环境变量示例：

```bash
# Linux，路径以你下载的官方 SDK 和实际节点为准
export CH347_LIBRARY=/absolute/path/libch347.so
export CH347_DEVICE_PATH=/dev/ch34x_pis0
bash start.sh
```

```powershell
# Windows PowerShell
$env:CH347_LIBRARY = 'C:\WCH\CH347DLLA64.dll'
$env:CH347_DEVICE_INDEX = '0'
.\start-windows.bat
```

SDK 动态库名称可能随包变化，请填写实际文件；不自动下载 DLL。Linux WCH 字符设备驱动与 libusb 的接口占用可能冲突，切换后端前应停止占用者。SDK ctypes 绑定分别处理 Windows index 与 Linux fd，并使用 `_pack_=1`、固定宽度整数，SPIConfig 为 20 bytes。

## 推荐验收顺序

1. 不接目标板，分别以四种硬件模式上电；连接工作台，确认 PID、版本、串口与驱动识别结果。
2. UART 用 TX/RX 回环测试；模式 0 的两个端口分别验证。新板的 UART0 复用接线以原理图为准。
3. 使用已知 I²C 器件，只读器件标识；随后在可恢复寄存器测试写入。检查模式 1 / 2 ACK 和返回长度。
4. 用独立测试 Flash 进行识别、完整备份、擦除、写入、再次读回比较 SHA-256。
5. JTAG 在 1 MHz 读取稳定 IDCODE；FPGA 先 SRAM 测试设计，再测试配置 Flash 掉电重载。
6. 对支持的 MCU 测试下载校验、复位、暂停、单步、寄存器、内存与外部 GDB。
7. 最后验证 GPIO 与实验性 XVC；观察实际波形、TDO 时序和 Vivado/ILA 行为。

不能用这个软件补足硬件缺失：+3V3 是输出而不是 VTref；若新版要调试 1.8 V 等目标需对应电平转换和方向设计。CH347T 2.41 无原生 SWD，4.41/5.44 有相关限制；本实现 SWD 保守限制 1 MHz。它不是示波器、逻辑分析仪或自动支持任意 MCU 的通用探针。

## 执行与数据策略

- Agent 仅监听 `127.0.0.1`。API 使用启动时随机 Bearer token，检查 Host 和精确 Origin，阻止外网页跨站调用与 DNS rebinding。
- 文件只传给本机 Agent。最多 64 MiB；内部随机文件名；执行前重新比对 SHA-256。上传文件不能成为任意配置脚本或 shell 命令。
- 所有任务先生成最多 5 分钟有效的计划。改变目标状态的操作需确认；同一个计划重复提交不会再次执行。
- 子进程全部参数化调用、无 shell；目标配置为白名单。总线事务在可终止的独立进程中执行；硬件任务互斥，失败不自动重试。
- 服务重启时把进行中的任务标记为 interrupted，绝不自动重放；目标可能处于部分写入状态，需要读回或校验。
- 文件、备份和最近 200 个任务日志保存在用户目录 `.ch347-studio`。程序不会自动删除固件；需要时在服务停止后由用户清理。历史记录会持久化，当前内存中的文件下载映射在服务重启后失效，文件本体仍留在目录内。
- 串口接收记录保留最近 3000 条；操作日志每任务最近 1500 行。关闭网页不会停止已启动的后台会话；使用“断开并停止会话”或在终端 Ctrl+C。
- 非 AI 路径不发送固件或设备数据到模型。启用 AI 后，用户问题和工具返回的设备状态/计划会发送给配置的模型服务；文件内容仍不作为模型附件发送。

## GDB 示例

在网页启动 MCU 调试后：

```gdb
target extended-remote 127.0.0.1:3333
monitor halt
info registers
x/16wx 0x20000000
```

若在外部 GDB 操作目标，应避免同时点击网页调试控制。自定义目标需要在 `bridge/core.py` 的 TARGETS 白名单中添加经过核实的脚本，并更新前端列表；当前网页不接受任意 OpenOCD 配置文件。

## 可选 AI Agent

普通功能完全不依赖模型。`agent-runtime/` 使用 eve，默认模型保留 scaffold 的 `openai/gpt-6-luna-fast`，工具只有读取状态和准备计划；禁用默认 shell、文件和网页工具。

1. 使用 Node.js 24，在 `agent-runtime` 执行 `npm ci`。
2. 在本机配置可用的 AI Gateway 凭据（如 `AI_GATEWAY_API_KEY`），不要放进网页或提交到仓库。此交付未配置凭据，未执行付费模型调用。
3. 启动 Python Agent 前设置 `CH347_EVE_URL=http://127.0.0.1:2000`。启动 Python Agent 后，从终端获得本次配对码。
4. 在 **eve 所在终端** 设置 `CH347_BRIDGE_URL=http://127.0.0.1:8765` 和 `CH347_BRIDGE_TOKEN=本次配对码`，执行 `npx eve dev --no-ui`。若开发服务器端口不是 2000，更新 CH347_EVE_URL 并重新启动 Python Agent，同时更新 eve 的配对码。
5. 工作台刷新连接状态后显示 “EVE AI · 已配置”。这里只表示环境变量已设置；网络、密钥或模型失败时会明确报错。建议先运行 `npm run typecheck` 和 `npm run build`。

AI 返回的是建议与计划文本；最终仍需到相应模块确认执行。Agent 端模型调用不拥有 `/api/execute` 工具，不能绕过网页确认。

## 代码与测试

```text
dist/                独立网页：HTML / CSS / JavaScript
bridge/server.py     localhost HTTP、配对、CORS、上传与下载
bridge/core.py       计划验证、任务互斥、进程、OpenOCD/FPGA/Flash/UART
bridge/bus.py        WCH SDK ABI 与 HID 总线适配
bridge/xvc.py        实验性 CH347T 原始 USB XVC
agent-runtime/       可选 eve AI Agent，typed tools
requirements.txt     Python 依赖
start.sh             macOS / Linux 启动
start-windows.bat    Windows 启动
tests/               硬件隔离的软件测试
```

运行 `python -m unittest discover -s tests -v`。57 项 Python 测试覆盖 RP2040 采集协议、导出、UF2 校验，以及 CH347 的模式、版本、目标配置、文件完整性、计划确认与去重、子进程失败/取消、鉴权/Origin/Host、XVC 向量分包与 TCP 协议。测试使用受控模拟硬件，不能替代真机验收。

运行 `node --test tests/test_waveform.js` 可执行 4 项波形视图回归测试（测试需要 Node.js）。前端已通过浏览器检查缩放按钮、滚轮缩放、滑杆和波形拖动、游标保留，以及导航、计划生成、演示执行与记录；SHA-256 fallback 使用 4 个标准实现对照向量校验。eve 类型检查与生产构建通过，模型调用未测试。

## 参考来源

- WCH CH347 官方资料：https://www.wch.cn/products/CH347.html
- WCH Linux SDK：https://github.com/WCHSoftGroup/ch341par_linux
- WCH Linux ABI：https://github.com/WCHSoftGroup/ch341par_linux/blob/main/demo/ch347/ch347_lib.h
- openFPGALoader：https://github.com/trabucayre/openFPGALoader
- CH347 USB 协议核对：https://github.com/trabucayre/openFPGALoader/blob/master/src/ch347jtag.cpp
- XVC 支持范围核对：https://github.com/trabucayre/openFPGALoader/blob/master/src/xvc_server.cpp
- OpenOCD：https://github.com/openocd-org/openocd
- flashrom：https://github.com/flashrom/flashrom
- HID Python 实现：https://github.com/i2cy/CH347-HIDAPI

特别说明：openFPGALoader 支持 `ch347_jtag` 下载；经检查其 XVC 构造器尚未接入 CH347，且该实现未使用传入 IP 绑定地址。因此本项目没有直接调用 `openFPGALoader --xvc -c ch347_jtag`，而实现了只监听 loopback 的独立 XVC 后端。HID I²C 加入超时、返回长度与帧检查；HID GPIO 目前未开放。

## 生成完整启动包

```bash
python package_release.py dist/CH347_Debug_Studio.zip
```

这会生成网页“连接设置”中可下载的完整启动包；Git 仓库不重复提交这个生成文件。`dist/firmware/` 已包含三份专用 UF2、版本校验清单和完整对应源码包，克隆后即可使用。

## 工具汇总与硬件可视化

左侧「工具汇总」可下载两块板的原始 KiCad 9 工程，并在线查看带图纸外框和标题栏的原理图、PCB 双层叠加 / 正反面及可旋转的 3D 装配模型。PCB 可点击走线、焊盘或过孔，高亮整个网络并显示名称和连接的管脚。板卡图片与 3D 均保留原始管脚丝印；各功能页显示实际 J2 脚号、板上丝印和当前功能，随 ADC、GPIO、UART 与总线选择更新。详见 [硬件资料与重建说明](docs/HARDWARE.md)。

验证：`python -m unittest discover -s tests -v`（57 项），`node --test tests/test_waveform.js tests/test_hardware.js tests/test_pcb_viewer.js`（13 项）。硬件资料校验包括原文件哈希、正反面焊盘、丝印对应、引脚映射与本地静态资源类型。
