// Geometry and hit testing use the PCB's original millimetre coordinates.
export const copperLayers=side=>side==='front'?['F.Cu']:side==='back'?['B.Cu']:['B.Cu','F.Cu'];
export const padOnLayer=(pad,layer)=>pad.layers.includes(layer)||pad.layers.includes('*.Cu');
export function segmentDistance(x,y,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy,t=length?Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/length)):0;return Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy);}
export function arcGeometry(a,m,b){const d=2*(a[0]*(m[1]-b[1])+m[0]*(b[1]-a[1])+b[0]*(a[1]-m[1]));if(Math.abs(d)<1e-10)return null;const aa=a[0]**2+a[1]**2,mm=m[0]**2+m[1]**2,bb=b[0]**2+b[1]**2,x=(aa*(m[1]-b[1])+mm*(b[1]-a[1])+bb*(a[1]-m[1]))/d,y=(aa*(b[0]-m[0])+mm*(a[0]-b[0])+bb*(m[0]-a[0]))/d,r=Math.hypot(a[0]-x,a[1]-y),angle=p=>Math.atan2(p[1]-y,p[0]-x),start=angle(a),end=angle(b),mid=angle(m),tau=2*Math.PI,positive=n=>(n%tau+tau)%tau,sweep=positive(mid-start)<=positive(end-start)?1:0,span=sweep?positive(end-start):positive(start-end);return {x,y,r,start,span,sweep};}
export function arcPath(t){const a=arcGeometry(t.start,t.mid,t.end);return a?`M ${t.start.join(' ')} A ${a.r} ${a.r} 0 ${a.span>Math.PI?1:0} ${a.sweep} ${t.end.join(' ')}`:`M ${t.start.join(' ')} L ${t.end.join(' ')}`;}
export function pointInPolygon(x,y,points){let inside=false;for(let i=0,j=points.length-1;i<points.length;j=i++){const a=points[i],b=points[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside;}return inside;}
export function padDistance(x,y,p){const a=p.angle*Math.PI/180,dx=x-p.x,dy=y-p.y,px=dx*Math.cos(a)-dy*Math.sin(a),py=dx*Math.sin(a)+dy*Math.cos(a),w=p.size[0]/2,h=p.size[1]/2;
 if(p.shape==='circle')return Math.max(0,Math.hypot(px,py)-w);
 const r=p.shape==='oval'?Math.min(w,h):p.shape==='roundrect'?Math.min(w,h)*2*p.roundrect_ratio:0;
 const qx=Math.abs(px)-(w-r),qy=Math.abs(py)-(h-r);return Math.max(0,Math.hypot(Math.max(qx,0),Math.max(qy,0))+Math.min(Math.max(qx,qy),0)-r);
}
export function hitNets(data,x,y,side,tolerance=.15){const layers=copperLayers(side),hits=new Map();const add=(id,dist,layer,kind)=>{if(dist>tolerance||!id)return;const hit=hits.get(id);if(!hit||dist<hit.distance)hits.set(id,{id,distance:dist,layer,kind});};
 for(const t of data.tracks){if(!layers.includes(t.layer))continue;let distance=segmentDistance(x,y,t.start,t.end);if(t.kind==='arc'){const a=arcGeometry(t.start,t.mid,t.end);if(a){const angle=Math.atan2(y-a.y,x-a.x),delta=((a.sweep?angle-a.start:a.start-angle)%(2*Math.PI)+2*Math.PI)%(2*Math.PI);distance=delta<=a.span?Math.abs(Math.hypot(x-a.x,y-a.y)-a.r):Math.min(Math.hypot(x-t.start[0],y-t.start[1]),Math.hypot(x-t.end[0],y-t.end[1]));}}add(t.net_id,Math.max(0,distance-t.width/2),t.layer,'track');}
 for(const c of data.components)for(const p of c.pads){const layer=layers.find(l=>padOnLayer(p,l));if(layer)add(p.net_id,padDistance(x,y,p),layer,'pad');}
 for(const v of data.vias)if(layers.some(l=>v.layers.includes(l)))add(v.net_id,Math.max(0,Math.hypot(x-v.at[0],y-v.at[1])-v.size/2),'F.Cu / B.Cu','via');
 // Filled planes only win when no nearby trace/pad/via exists.
 if(!hits.size)for(const z of data.zones)if(layers.includes(z.layer)&&pointInPolygon(x,y,z.points))add(z.net_id,0,z.layer,'zone');
 return [...hits.values()].sort((a,b)=>a.distance-b.distance||layers.indexOf(b.layer)-layers.indexOf(a.layer)||a.id-b.id);
}
export function netDetails(data,id){const pins=[];for(const c of data.components)for(const p of c.pads)if(p.net_id===id&&p.number)pins.push(`${c.ref}-${p.number}`);return {name:data.nets[id]||`网络 ${id}`,pins:[...new Set(pins)],layers:[...new Set([...data.tracks.filter(t=>t.net_id===id).map(t=>t.layer),...data.zones.filter(z=>z.net_id===id).map(z=>z.layer),...data.components.flatMap(c=>c.pads.filter(p=>p.net_id===id).flatMap(p=>['F.Cu','B.Cu'].filter(l=>padOnLayer(p,l))))])].sort()};}
