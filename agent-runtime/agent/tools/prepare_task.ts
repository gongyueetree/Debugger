import { defineTool } from "eve/tools";
import { z } from "zod";
import { bridge } from "../../lib/bridge.js";
export default defineTool({
  description: "验证并生成 CH347 / RP2040 操作计划。只准备，不执行。文件必须先在网页上传，不能虚构 file_id。用户仍需在网页核对参数并确认执行。",
  inputSchema: z.object({
    device_id: z.string(),
    op: z.enum(["fpga.detect","fpga.sram","fpga.flash","flash.detect","flash.read","flash.write","flash.verify","flash.erase","mcu.start","mcu.stop","mcu.halt","mcu.resume","mcu.step","mcu.reset","mcu.registers","mcu.memory","mcu.program","uart.open","uart.close","uart.send","i2c.scan","i2c.read","i2c.write","spi.transfer","gpio.read","gpio.write","jtag.svf","xvc.start","xvc.stop","logic.capture","scope.capture"]),
    params: z.record(z.string(),z.union([z.string(),z.number(),z.boolean()])),
  }),
  async execute(input) {
    const plan=await bridge("prepare",input);
    const { confirmation, ...review }=plan;
    return {...review,note:"计划尚未执行。到对应网页模块核对参数并生成可确认计划。"};
  },
});
