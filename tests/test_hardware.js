import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {BOARDS,RP,pinProfile,rpKey} from '../dist/hardware-data.js';
const geometry=b=>JSON.parse(readFileSync(new URL(`../dist/hardware/${b}/geometry.json`,import.meta.url)));
test('every displayed silk label agrees with its nearest same-side J2 pad in the PCB',()=>{
 for(const key of Object.keys(BOARDS)){
  const g=geometry(key),pads=g.connectors.find(c=>c.ref==='J2').pads;
  for(const pad of pads){const layer=+pad.number%2?'F.SilkS':'B.SilkS';const silk=g.silkscreen.filter(t=>t.layer===layer&&t.at[2]===0&&Math.abs(t.at[1]-pad.y)<.7).sort((a,b)=>Math.abs(a.at[0]-pad.x)-Math.abs(b.at[0]-pad.x))[0],want=BOARDS[key].silk[+pad.number-1];if(want==='—')assert.equal(silk,undefined);else assert.equal(silk.text.trim(),want);}
 }
});
test('ADC selection connects the exact ADC net, retaining the CH6/7/8 board labels',()=>{
 const pads=geometry('rp2040').connectors.find(c=>c.ref==='J2').pads;
 for(let channel=0;channel<3;channel++){const p=pinProfile('scope',7,{channel},'i2c','rp2040'),pin=8+channel*2;assert.equal(pads.find(x=>+x.number===pin).net,`/IO${26+channel}`);assert.deepEqual(Object.keys(p.active),['1',String(pin)]);assert.equal(BOARDS.rp2040.silk[pin-1],`CH${6+channel}`);}
});
test('logic and DAP signal mappings agree with firmware-facing board nets',()=>{
 const pads=geometry('rp2040').connectors.find(c=>c.ref==='J2').pads;
 for(const [pin,signal] of Object.entries(pinProfile('logic',5,{trigger:'rising',trigger_channel:5},'i2c','rp2040').active)){if(signal.kind==='ground')continue;const gp=signal.signal.split(' · ')[1];assert.equal(pads.find(x=>x.number===pin).net,'/'+gp.replace('GP','IO'));}
 const p=pinProfile('mcu',4,{transport:'swd'},'i2c','rp2040');assert.match(p.active[3].signal,/SWCLK/);assert.match(p.active[5].signal,/SWDIO/);assert.equal(pinProfile('logic',5,{trigger:'rising',trigger_channel:5},'i2c','rp2040').active[6].kind,'trigger');
});
test('bus, GPIO and UART choices never reuse another mode mapping',()=>{
 assert.deepEqual(Object.keys(pinProfile('i2c',1,{},'i2c').active),['10','11','12']);assert.deepEqual(Object.keys(pinProfile('i2c',1,{},'spi').active),['1','3','5','7','11']);assert.ok(pinProfile('gpio',3,{pin:6}).active[4]);assert.ok(pinProfile('uart',0,{channel:0}).active[12]);assert.ok(pinProfile('uart',3,{channel:0}).active[6]);assert.ok(pinProfile('uart',4,{},'i2c','rp2040').active[11]);
 assert.equal(pinProfile('mcu',3,{transport:'swd'}).verified,false);assert.deepEqual(Object.keys(pinProfile('mcu',3,{transport:'swd'}).active),['11']);
});
test('V2 is the default RP2040 board and its wiring agrees with the generated PCB nets',()=>{
 const pads=geometry('rp2040v2').connectors.find(c=>c.ref==='J2').pads,net=pin=>pads.find(x=>+x.number===+pin).net;
 assert.equal(rpKey(null),'rp2040v2');assert.equal(rpKey({family:'rp2040',board:'v2'}),'rp2040v2');assert.equal(rpKey({family:'rp2040',board:'v1'}),'rp2040');assert.equal(pads.length,16);assert.equal(BOARDS.rp2040v2.pins.length,16);
 const logic=pinProfile('logic',5,{trigger:'rising',trigger_channel:3});assert.equal(logic.board,'rp2040v2');
 RP.rp2040v2.logicPins.forEach((pin,i)=>{assert.equal(net(pin),'/IO'+i);assert.equal(logic.active[pin].signal,`D${i} · GP${RP.rp2040v2.logicGpio[i]}`);});assert.equal(logic.active[9].kind,'trigger');assert.equal(net(1),'/VIO');
 for(let channel=0;channel<3;channel++){const p=pinProfile('scope',7,{channel}),pin=RP.rp2040v2.adcPins[channel];assert.equal(net(pin),'/AIN'+channel);assert.match(p.active[pin].signal,new RegExp('ADC'+channel));}
 const dap=pinProfile('mcu',4,{transport:'swd'});assert.match(dap.active[3].signal,/SWCLK/);assert.equal(net(3),'/IO0');assert.match(dap.active[5].signal,/SWDIO/);assert.equal(net(5),'/IO1');assert.match(dap.active[7].signal,/nRESET/);assert.equal(net(7),'/IO2');
 const uart=pinProfile('uart',4,{});assert.match(uart.active[9].signal,/^TX/);assert.equal(net(9),'/IO3');assert.match(uart.active[11].signal,/^RX/);assert.equal(net(11),'/IO4');
 for(const p of [logic,dap,uart]){assert.equal(p.active[2].kind,'ground');assert.equal(net(2),'GND');}assert.equal(net(10),'GND');assert.equal(net(15),'GND');assert.equal(net(16),'/5V_OUT');
});

