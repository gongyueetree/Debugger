// Physical J2 numbering comes from the supplied KiCad boards. Odd = F.Cu, even = B.Cu.
export const BOARDS={
 ch347:{name:'CH347 Debugger',chip:'CH347T',silk:['TDO','3.3V','TDI','CTS','TCK','RXD','TMS','TXD','TRST','SCL','GND','SDA'],base:'CH347_SPI',zip:'CH347_Debug.zip',desc:'四模式调试 · JTAG / UART / SPI / I²C',pins:['TDO / MISO','+3V3','TDI / MOSI / TXD0','CTS1 / GPIO6','TCK / SCK','RXD1','TMS / CS0','TXD1','TRST / GPIO5','SCL / GPIO3','GND','SDA / RXD0']},
 rp2040:{name:'LA RP2040 V1',chip:'RP2040',size:'35 × 16.5 mm',silk:['GND','3V3','CH0','5V0','CH1','CH5','CH2','CH6','CH3','CH7','CH4','CH8'],base:'LA_rp2040',zip:'LA_RP2040.zip',desc:'SWD 调试 · 8 通道逻辑 · ADC 示波器 · 3.3 V 直连',pins:['GND','+3V3','GP20','USB +5V','GP21','GP25','GP22','GP26 / ADC0','GP23','GP27 / ADC1','GP24','GP28 / ADC2']},
 rp2040v2:{name:'LA RP2040 V2',chip:'RP2040',size:'58 × 21 mm',silk:['VREF','GND','IO0','IO5','IO1','IO6','IO2','IO7','IO3','—','IO4','—','A0','—','GND','5V'],base:'LA_RP2040_V2',zip:'LA_RP2040_V2.zip',desc:'电平转换 1.65–5.5 V · 端口保护 · 兼容官方 Debug Probe 固件',pins:['VREF · 目标参考电压','GND','IO0 · GP12','IO5 · GP23','IO1 · GP14 / GP13','IO6 · GP24','IO2 · GP20','IO7 · GP25','IO3 · GP4','GND','IO4 · GP5','A1 · GP27','A0 · GP26','A2 · GP28','GND','+5V 输出']}
};
BOARDS.ch347.size='35 × 16.5 mm';
// Firmware-facing wiring of the two RP2040 board revisions. Pin numbers are J2 pad numbers.
export const RP={
 rp2040:{label:'LA_RP2040 V1',prefix:'la-rp2040-',logicGpio:[20,21,22,23,24,25,26,27],logicPins:[3,5,7,9,11,6,8,10],logicMax:100000,adcPins:[8,10,12],swclk:[3,'GP20'],swdio:[5,'GP21'],reset:[7,'GP22'],tx:[11,'GP24'],rx:[6,'GP25'],ground:1,levels:'输入为 3.3 V 逻辑电平。',adcNote:'输入直接连接 RP2040 ADC，没有衰减或隔离前端。'},
 rp2040v2:{label:'LA_RP2040 V2',prefix:'la-rp2040-v2-',logicGpio:[12,13,20,4,5,23,24,25],logicPins:[3,5,7,9,11,4,6,8],logicMax:50000,adcPins:[13,12,14],swclk:[3,'IO0 · GP12'],swdio:[5,'IO1 · GP14 / GP13'],reset:[7,'IO2 · GP20'],tx:[9,'IO3 · GP4'],rx:[11,'IO4 · GP5'],ground:2,vref:1,levels:'输入经 74LVC1T45 电平转换，逻辑电平跟随 VREF（1.65–5.5 V）。',adcNote:'输入经 2.2 kΩ 与钳位二极管进入 RP2040 ADC，量程 0–3.3 V，不经过电平转换。'}
};
// V2 is the current hardware; a connected board running the V1 builds is recognised by its USB product string.
export const rpKey=device=>device?.family==='rp2040'&&device.board==='v1'?'rp2040':'rp2040v2';
export function pinProfile(page,mode,form={},bus='i2c',rp='rp2040v2'){
 const R=RP[rp]||RP.rp2040v2;rp=RP[rp]?rp:'rp2040v2';
 const board=['logic','scope'].includes(page)?rp:['mcu','uart','wiring','firmwares'].includes(page)&&mode>=4?rp:'ch347';const isRp=board!=='ch347';
 const active={}, add=(pin,signal,target,kind='signal')=>{active[pin]={signal,target,kind};};
 let title='',note='',required='',verified=true;
 if(page==='logic'){
  title='8 通道逻辑采集'; required='SUMP8 固件';
  R.logicPins.forEach((pin,i)=>add(pin,'D'+i+' · GP'+R.logicGpio[i],'目标数字信号'+(form.trigger!=='none'&&+form.trigger_channel===i?' · 触发通道':''),form.trigger!=='none'&&+form.trigger_channel===i?'trigger':'signal'));
  note='所有 8 路同步采集。'+R.levels;if(R.vref)add(R.vref,'VREF','← 目标 VCC（开关拨到 EXT）','optional');
 }else if(page==='scope'){
  const ch=Math.max(0,Math.min(2,+form.channel||0));title='ADC'+ch+' 单路采集';required='ADC12 固件';add(R.adcPins[ch],'ADC'+ch+' · GP'+(26+ch),'模拟信号输入 · 0–3.3 V');note=R.adcNote;
 }else if(page==='mcu'&&isRp){
  title='CMSIS-DAP · SWD';required='DAP 固件';add(R.swclk[0],'SWCLK · '+R.swclk[1],'→ 目标 SWCLK');add(R.swdio[0],'SWDIO · '+R.swdio[1],'↔ 目标 SWDIO');add(R.reset[0],'nRESET · '+R.reset[1],'→ 目标复位（可选）','optional');if(R.vref)add(R.vref,'VREF','← 目标 VCC（开关拨到 EXT）；INT 档由调试器提供约 3.0 V','optional');note=R.vref?'管脚与官方 Raspberry Pi Debug Probe 一致；官方固件可直接使用（无 nRESET）。':'使用本工具提供的 LA_RP2040 DAP 固件映射。';
 }else if(page==='mcu'&&form.transport==='swd'){
  title='CH347 · SWD';required='模式 3 · 兼容版本';verified=false;note='此工程只标注 JTAG 复用网络，原生 SWD 接线尚未完成芯片版本核验；这里不推测 SWDIO / SWCLK。请先核对驱动与芯片资料，或选用 RP2040 DAP。';
 }else if(['fpga','jtag','mcu'].includes(page)){
  title=page==='fpga'?'FPGA · JTAG':page==='jtag'?'SVF / XVC · JTAG':'MCU · JTAG';required='CH347 模式 3';
  [[5,'TCK','→ 目标 TCK'],[7,'TMS','→ 目标 TMS'],[3,'TDI','→ 目标 TDI'],[1,'TDO','← 目标 TDO']].forEach(x=>add(...x));add(9,'nTRST','→ TAP 复位（按目标需要）','optional');note='nTRST 是 TAP 复位，不等于目标系统 nRESET。';
 }else if(page==='uart'){
  if(isRp){title='CDC UART';required='DAP 固件';add(R.tx[0],'TX · '+R.tx[1],'→ 目标 RX');add(R.rx[0],'RX · '+R.rx[1],'← 目标 TX');}
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
 }else{title='完整接口参考';required=isRp?'按固件切换功能':'按硬件模式切换功能';}
 add(isRp?R.ground:11,'GND','↔ 目标 GND · 必须共地','ground');
 return {board,title,note,required,verified,active};
}
