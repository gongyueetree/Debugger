// Physical J2 numbering comes from the supplied KiCad boards. Odd = F.Cu, even = B.Cu.
export const BOARDS={
 ch347:{name:'CH347 Debugger',chip:'CH347T',silk:['TDO','3.3V','TDI','CTS','TCK','RXD','TMS','TXD','TRST','SCL','GND','SDA'],base:'CH347_SPI',zip:'CH347_Debug.zip',desc:'四模式调试 · JTAG / UART / SPI / I²C',pins:['TDO / MISO','+3V3','TDI / MOSI / TXD0','CTS1 / GPIO6','TCK / SCK','RXD1','TMS / CS0','TXD1','TRST / GPIO5','SCL / GPIO3','GND','SDA / RXD0']},
 rp2040:{name:'LA RP2040',chip:'RP2040',silk:['GND','3V3','CH0','5V0','CH1','CH5','CH2','CH6','CH3','CH7','CH4','CH8'],base:'LA_rp2040',zip:'LA_RP2040.zip',desc:'SWD 调试 · 8 通道逻辑 · ADC 示波器',pins:['GND','+3V3','GP20','USB +5V','GP21','GP25','GP22','GP26 / ADC0','GP23','GP27 / ADC1','GP24','GP28 / ADC2']}
};
export function pinProfile(page,mode,form={},bus='i2c'){
 const board=['logic','scope'].includes(page)?'rp2040':['mcu','uart','wiring','firmwares'].includes(page)&&mode>=4?'rp2040':'ch347';
 const active={}, add=(pin,signal,target,kind='signal')=>{active[pin]={signal,target,kind};};
 let title='',note='',required='',verified=true;
 if(page==='logic'){
  title='8 通道逻辑采集'; required='SUMP8 固件';
  [3,5,7,9,11,6,8,10].forEach((pin,i)=>add(pin,'D'+i+' · GP'+(20+i),'目标数字信号'+(form.trigger!=='none'&&+form.trigger_channel===i?' · 触发通道':''),form.trigger!=='none'&&+form.trigger_channel===i?'trigger':'signal'));
  note='所有 8 路同步采集。输入为 3.3 V 逻辑电平。';
 }else if(page==='scope'){
  const ch=Math.max(0,Math.min(2,+form.channel||0));title='ADC'+ch+' 单路采集';required='ADC12 固件';add(8+2*ch,'ADC'+ch+' · GP'+(26+ch),'模拟信号输入 · 0–3.3 V');note='输入直接连接 RP2040 ADC，没有衰减或隔离前端。';
 }else if(page==='mcu'&&board==='rp2040'){
  title='CMSIS-DAP · SWD';required='DAP 固件';add(3,'SWCLK · GP20','→ 目标 SWCLK');add(5,'SWDIO · GP21','↔ 目标 SWDIO');add(7,'nRESET · GP22','→ 目标复位（可选）','optional');note='使用本工具提供的 LA_RP2040 DAP 固件映射。';
 }else if(page==='mcu'&&form.transport==='swd'){
  title='CH347 · SWD';required='模式 3 · 兼容版本';verified=false;note='此工程只标注 JTAG 复用网络，原生 SWD 接线尚未完成芯片版本核验；这里不推测 SWDIO / SWCLK。请先核对驱动与芯片资料，或选用 RP2040 DAP。';
 }else if(['fpga','jtag','mcu'].includes(page)){
  title=page==='fpga'?'FPGA · JTAG':page==='jtag'?'SVF / XVC · JTAG':'MCU · JTAG';required='CH347 模式 3';
  [[5,'TCK','→ 目标 TCK'],[7,'TMS','→ 目标 TMS'],[3,'TDI','→ 目标 TDI'],[1,'TDO','← 目标 TDO']].forEach(x=>add(...x));add(9,'nTRST','→ TAP 复位（按目标需要）','optional');note='nTRST 是 TAP 复位，不等于目标系统 nRESET。';
 }else if(page==='uart'){
  if(board==='rp2040'){title='CDC UART';required='DAP 固件';add(11,'TX · GP24','→ 目标 RX');add(6,'RX · GP25','← 目标 TX');}
  else{const channel=mode===0&&+form.channel===0?0:1;title='UART'+channel;required=channel===0?'CH347 模式 0':'CH347 UART1';add(channel===0?3:8,'TXD'+channel,'→ 目标 RX');add(channel===0?12:6,'RXD'+channel,'← 目标 TX');}
  note='TX 与目标 RX 交叉连接。UART 通道标记必须与所选系统串口一致。';
 }else if(page==='flash'||page==='i2c'&&bus==='spi'){
  title=page==='flash'?'SPI Flash':'SPI · CS0';required=page==='flash'?'CH347 模式 1':'CH347 模式 1 / 2';
  [[1,'MISO','← 目标 DO / MISO'],[3,'MOSI','→ 目标 DI / MOSI'],[5,'SCK','→ 目标 CLK'],[7,'CS0','→ 目标 CS#']].forEach(x=>add(...x));
  note='本工具使用 CS0；按目标器件要求处理 WP# / HOLD# 等附加信号。';
 }else if(page==='i2c'){
  title='I²C';required='CH347 模式 1 / 2';add(10,'SCL','↔ 目标 SCL');add(12,'SDA','↔ 目标 SDA');note='SCL / SDA 需要合适的 3.3 V 上拉，先核对目标板电路。';
 }else if(page==='gpio'){
  const gpio=[3,5,6].includes(+form.pin)?+form.pin:3;title='GPIO'+gpio;required='CH347 模式 3';add({3:10,5:9,6:4}[gpio],'GPIO'+gpio,'↔ 目标数字 I/O');note='设置输出会改变引脚方向。GPIO3 / 5 / 6 与其他接口复用。';
 }else{title='完整接口参考';required=board==='rp2040'?'按固件切换功能':'按硬件模式切换功能';}
 add(board==='rp2040'?1:11,'GND','↔ 目标 GND · 必须共地','ground');
 return {board,title,note,required,verified,active};
}
