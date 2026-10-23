import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {hitNets,padDistance,arcGeometry,arcPath,netDetails} from '../dist/pcb-geometry.js';
const load=b=>JSON.parse(readFileSync(new URL(`../dist/hardware/${b}/geometry.json`,import.meta.url)));
test('every real trace can be selected at its midpoint on its actual copper layer',()=>{
 for(const board of ['ch347','rp2040']){const data=load(board);for(const t of data.tracks){const x=(t.start[0]+t.end[0])/2,y=(t.start[1]+t.end[1])/2;assert.ok(hitNets(data,x,y,t.layer==='F.Cu'?'front':'back',.01).some(h=>h.id===t.net_id),`${board}: ${data.nets[t.net_id]} ${t.layer}`);}}
});
test('overlapping front/back pads offer both nets, but single-side views do not select the hidden face',()=>{
 const data=load('ch347'),p=data.connectors.find(c=>c.ref==='J2').pads.find(p=>p.number==='1');
 const both=hitNets(data,p.x,p.y,'both',.01).map(h=>data.nets[h.id]);assert.ok(both.includes('/MISO{slash}TDO'));assert.ok(both.includes('+3V3'));
 assert.deepEqual(hitNets(data,p.x,p.y,'front',.01).map(h=>data.nets[h.id]),['/MISO{slash}TDO']);
 assert.deepEqual(hitNets(data,p.x,p.y,'back',.01).map(h=>data.nets[h.id]),['+3V3']);
});
test('selection retains the PCB net name and finds connected component pins across both faces',()=>{
 const data=load('rp2040'),id=+Object.keys(data.nets).find(id=>data.nets[id]==='/IO26'),d=netDetails(data,id);assert.equal(d.name,'/IO26');assert.ok(d.pins.includes('J2-8'));assert.ok(d.pins.some(pin=>pin.startsWith('U2-')));assert.ok(d.layers.includes('B.Cu'));
});
test('rotated pads use world orientation and rounded corners do not hit outside copper',()=>{
 const p={x:0,y:0,size:[4,1],angle:90,shape:'rect',roundrect_ratio:0};assert.equal(padDistance(0,1.8,p),0);assert.ok(padDistance(1.8,0,p)>1);assert.ok(padDistance(1,1,{...p,size:[2,2],angle:0,shape:'roundrect',roundrect_ratio:.5})>0);
});
test('arc geometry retains the true sweep and areas outside the PCB are not selectable',()=>{
 const a=arcGeometry([1,0],[0,1],[-1,0]);assert.ok(Math.abs(a.r-1)<1e-8);assert.equal(a.sweep,1);assert.match(arcPath({start:[1,0],mid:[0,1],end:[-1,0]}),/ A /);assert.deepEqual(hitNets(load('rp2040'),0,0,'both',.1),[]);
});
