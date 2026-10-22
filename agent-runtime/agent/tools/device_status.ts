import { defineTool } from "eve/tools";
import { z } from "zod";
import { bridge } from "../../lib/bridge.js";
export default defineTool({
  description: "读取本机 CH347 枚举结果、实际模式和工具可用性。不访问目标存储，不执行写入。",
  inputSchema: z.object({}),
  async execute() { return bridge("status"); },
});
