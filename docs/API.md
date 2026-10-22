# 本地 HTTP API

基址 `http://127.0.0.1:8765/api`。每个请求携带 `Authorization: Bearer <本次配对码>`。POST 为 application/json。仅本机 Host 与明确允许的 Origin 可访问。没有远程监听、任意命令、任意目标脚本或自动模式切换 API。

| 路径 | 方法 | 用途 |
|---|---|---|
| /status | GET | USB 实际设备、版本、端口、工具与服务状态 |
| /upload | POST | `{name,data}`，data 为 Base64；返回 id、size、SHA-256 |
| /prepare | POST | `{op,device_id,params}`；校验模式/版本/依赖/数据，返回计划、命令预览及确认值 |
| /execute | POST | `{plan_id,confirmation}`；状态修改任务必须匹配本次确认值 |
| /jobs | GET | 最近的任务，含结果和日志 |
| /jobs/{id} | GET | 单个任务状态 |
| /cancel | POST | `{job_id}`，请求停止；不是硬件回滚 |
| /download/{id} | GET | 当前进程中的备份文件 |
| /uart | GET | 最近的串口 RX/TX 日志 |
| /disconnect | POST | 当前任务结束后停止调试/XVC/串口会话 |
| /assistant | POST | 可选 eve 模型助手；未启用时明确报错 |

任务状态为 queued → running → succeeded / failed / cancelled。服务重启中断的任务为 interrupted。

`op` 白名单及参数校验见 `bridge/core.py`。示例：

```json
{"op":"fpga.detect","device_id":"1:2:55dd","params":{"freq":1000000}}
```

本地 API 的确认机制是应用内防误操作流程，不是对持有本地 token 的恶意客户端的安全隔离。token 等同本机硬件操作权限，不应向不受信任页面或进程披露。

## RP2040 v0.2

设备增加 `family`、`profile`、`product`、`port`、`board_match`。`mode` 4/5/7 是 Agent 的固件配置编号：CMSIS-DAP / SUMP8 / ADC12；6 为未知或 BOOTSEL。不可当作 CH347 的硬件模式。CH347 原接口保持兼容。

`logic.capture` 参数：`rate`（100000/200000/500000/1000000/2000000/5000000/10000000/20000000）、`samples`（4–100000，4 的倍数）、`trigger`（none/rising/falling/high/low）、`trigger_channel`（0–7）、`timeout`（2–60秒）。串口由选中的真实设备决定，忽略调用者提供的 `port`。

`scope.capture` 参数：`rate`（10000/20000/50000/100000/200000/250000/500000）、`samples`（4–32768）、`channel`（0/1/2）、`vref`（2.5–3.3V）、`timeout`。返回 `capture`、`measurements`、`samples_b64`、`downloads`。ADC 原始数据为无符号 16bit 小端，每个码必须在0–4095；逻辑原始数据每样本1byte、时间正序、bit0=D0。

采集也通过 prepare→execute→jobs 流程，属于只读任务；取消用同一 cancel API。文件通过带配对码的 `/api/download/{id}` 获取。不能通过 HTTP 指定任意串口或执行任意 shell。
