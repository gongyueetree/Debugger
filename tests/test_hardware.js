import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {BOARDS,pinProfile} from '../dist/hardware-data.js';
const geometry=b=>JSON.parse(readFileSync(new URL(`../dist/hardware/${b}/geometry.json`,import.meta.url)));
test('every displayed silk label agrees with its nearest same-side J2 pad in the PCB',()=>{
 for(const key of Object.keys(BOARDS)){
  const g=geometry(key),pads=g.connectors.find(c=>c.ref==='J2').pads;
  for(const pad of pads){const layer=+pad.number%2?'F.SilkS':'B.SilkS';const silk=g.silkscreen.filter(t=>t.layer===layer&&t.at[2]===0&&Math.abs(t.at[1]-pad.y)<.7).sort((a,b)=>Math.abs(a.at[0]-pad.x)-Math.abs(b.at[0]-pad.x))[0];assert.equal(silk.text.trim(),BOARDS[key].silk[+pad.number-1]);}
 }
});
test('ADC selection connects the exact ADC net, retaining the CH6/7/8 board labels',()=>{
 const pads=geometry('rp2040').connectors.find(c=>c.ref==='J2').pads;
 for(let channel=0;channel<3;channel++){const p=pinProfile('scope',7,{channel}),pin=8+channel*2;assert.equal(pads.find(x=>+x.number===pin).net,`/IO${26+channel}`);assert.deepEqual(Object.keys(p.active),['1',String(pin)]);assert.equal(BOARDS.rp2040.silk[pin-1],`CH${6+channel}`);}
});
test('logic and DAP signal mappings agree with firmware-facing board nets',()=>{
 const pads=geometry('rp2040').connectors.find(c=>c.ref==='J2').pads;
 for(const [pin,signal] of Object.entries(pinProfile('logic',5,{trigger:'rising',trigger_channel:5}).active)){if(signal.kind==='ground')continue;const gp=signal.signal.split(' · ')[1];assert.equal(pads.find(x=>x.number===pin).net,'/'+gp.replace('GP','IO'));}
 const p=pinProfile('mcu',4,{transport:'swd'});assert.match(p.active[3].signal,/SWCLK/);assert.match(p.active[5].signal,/SWDIO/);assert.equal(pinProfile('logic',5,{trigger:'rising',trigger_channel:5}).active[6].kind,'trigger');
});
test('bus, GPIO and UART choices never reuse another mode mapping',()=>{
 assert.deepEqual(Object.keys(pinProfile('i2c',1,{},'i2c').active),['10','11','12']);assert.deepEqual(Object.keys(pinProfile('i2c',1,{},'spi').active),['1','3','5','7','11']);assert.ok(pinProfile('gpio',3,{pin:6}).active[4]);assert.ok(pinProfile('uart',0,{channel:0}).active[12]);assert.ok(pinProfile('uart',3,{channel:0}).active[6]);assert.ok(pinProfile('uart',4,{}).active[11]);
 assert.equal(pinProfile('mcu',3,{transport:'swd'}).verified,false);assert.deepEqual(Object.keys(pinProfile('mcu',3,{transport:'swd'}).active),['11']);
});
