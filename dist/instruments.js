import { MIN_WINDOW, normalizeView, resizeView, formatSampleTime as formatTime } from './wave-view.js';
// Acquisition views share the same validated prepare/execute path as programmers.
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const PIN_ROWS=[['1','GND','GND','GND','GND'],['2','+3V3','电源输出','电源输出','电源输出'],['3','GP20','SWCLK','D0','—'],['4','+5V','USB 电源输出','USB 电源输出','USB 电源输出'],['5','GP21','SWDIO','D1','—'],['6','GP25','UART RX','D5','—'],['7','GP22','目标 nRESET','D2','—'],['8','GP26','—','D6','ADC0'],['9','GP23','—','D3','—'],['10','GP27','—','D7','ADC1'],['11','GP24','UART TX','D4','—'],['12','GP28','—','保留','ADC2']];
export const modeName=n=>['CH347 · 双 UART','CH347 · SPI / I²C','CH347 · HID','CH347 · JTAG / SWD','RP2040 · SWD / UART','RP2040 · 逻辑分析','RP2040 · 待装固件','RP2040 · ADC 示波器'][n]||'未识别';
export const firmwareCards=()=>`<div class="firmware-grid">${[
 ['dap','01','SWD 调试 + UART','CMSIS-DAP v2 · OpenOCD','GP20 / GP21 · UART GP24 / GP25'],
 ['sump8','02','8 通道逻辑分析','PIO + DMA · SUMP','GP20–GP27 · 100 kSa/s–20 MSa/s'],
 ['adc12','03','数字示波器','12 bit ADC + DMA','GP26 / GP27 / GP28 · 最高 500 kSa/s']
].map(([id,num,title,sub,pins])=>`<article class="panel firmware-card"><div class="eyebrow">PROFILE ${num}</div><h3>${title}</h3><p>${sub}</p><small>${pins}</small><a class="button primary" href="firmware/la-rp2040-${id}.uf2" download>下载专用 UF2 ↓</a></article>`).join('')}</div>`;
export function firmwarePage(){return `<div class="notice">固件按上传的 LA_RP2040 电路定制。三个配置需通过 BOOTSEL 切换，当前不同时运行。固件已编译，仍需你的板卡实测。</div>${firmwareCards()}<section class="panel" style="margin-top:24px"><div class="panel-header"><h2>刷写与恢复</h2><span class="pill">USB BOOTSEL</span></div><div class="panel-body"><ol class="steps"><li>断开目标接线，按住板上的 BOOT 按钮，再插入 USB。</li><li>出现 RPI-RP2 磁盘后，将所需的专用 UF2 拖入该磁盘。</li><li>等待板卡重新枚举，回工作台点击“刷新”，选择 RP2040。</li><li>按下方表格连接信号；更换配置时重复以上步骤。</li></ol><p>原版 Pico 固件的默认 GPIO 与此板不一致。下载前可核对 <a href="firmware/manifest.json" target="_blank" rel="noopener">版本与 SHA-256</a>；对应的 <a href="firmware/firmware-sources.tar.gz" download>完整固件源码与许可证</a> 可用于重编译。</p></div></section>${rpWiring()}`}
export function rpWiring(){return `<section class="panel" style="margin-top:24px"><div class="panel-header"><h2>LA_RP2040 · J2 接线</h2><span class="pill">2 × 6 · 按焊盘编号</span></div><div class="panel-body"><div class="warning">信号脚直接连接 RP2040，没有电平转换或模拟衰减。数字信号使用 3.3 V；ADC 输入 0–3.3 V、与目标共地。+3V3 / +5V 是电源输出，不是电压检测脚。ADC 电压不得为负或高于参考电压。</div><div class="table-scroll"><table><thead><tr><th>J2 脚号</th><th>网络</th><th>调试固件</th><th>逻辑分析固件</th><th>示波器固件</th></tr></thead><tbody>${PIN_ROWS.map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="subtle">GP0 为状态灯；板载 GD25Q64 为 8 MiB。GP26/27 在逻辑与模拟配置中复用。UART TX 接目标 RX，UART RX 接目标 TX。</p></div></section>`}
export function profileSelector(state){return `<div class="profile-bar"><div><b>${state.demo?'选择演示设备':'当前设备'}</b><small>${state.demo?'示例波形不会读取 USB':'设备功能来自实际 USB 枚举'}</small></div>${state.demo?`<select id="device-select" aria-label="演示设备">${[[3,'CH347 · 四模式'],[4,'RP2040 · SWD / UART'],[5,'RP2040 · 逻辑分析仪'],[7,'RP2040 · ADC 示波器']].map(([v,t])=>`<option value="${v}" ${(state.mode<=3?v===3:state.mode===v)?'selected':''}>${t}</option>`).join('')}</select>`:`<select id="device-select" aria-label="选择实际设备"><option value="">${state.status?.devices?.length?'选择要操作的设备':'未检测到设备'}</option>${(state.status?.devices||[]).map(d=>`<option value="${escapeHTML(d.id)}" ${state.device?.id===d.id?'selected':''}>${escapeHTML(d.name+' · '+(d.serial||d.id))}</option>`).join('')}</select>`}<button data-refresh class="small" ${state.demo?'disabled':''}>刷新</button><button data-nav="firmwares" class="small">RP2040 固件</button></div>`}

export function instrumentPage(ctx, analog=false){
 const {state,field,button,getform,output}=ctx,p=getform(state.page),op=analog?'scope.capture':'logic.capture';
 const rates=analog?[10000,20000,50000,100000,200000,250000,500000]:[100000,200000,500000,1000000,2000000,5000000,10000000,20000000];
 const rateLabel=n=>n>=1e6?(n/1e6)+' MSa/s':(n/1e3)+' kSa/s';
 const job=state.activeJob?.op===op?state.activeJob:null, result=job?.result,cap=result?.capture;
 return `${state.demo?'<div class="warning">DEMO · 波形由内置样本生成，未连接硬件。选择参数并运行演示可体验完整流程。</div>':''}<div class="instrument-layout"><section class="panel"><div class="panel-header"><h2>采集设置</h2><span class="pill">${analog?'ADC12':'SUMP8'}</span></div><div class="panel-body"><div class="form-grid">${field('采样率','rate',p.rate,{full:true,choices:rates.map(n=>[n,rateLabel(n)])})}${field('采样点数','samples',p.samples,{full:true,choices:(analog?[1024,4096,16384,32768]:[1024,4096,16384,65536,100000]).map(n=>[n,n.toLocaleString()+' 点'])})}${analog?field('模拟输入（单路）','channel',p.channel,{full:true,choices:[[0,'ADC0 · GP26 · J2-8'],[1,'ADC1 · GP27 · J2-10'],[2,'ADC2 · GP28 · J2-12']]})+field('ADC 参考电压 / V','vref',p.vref,{full:true,help:'默认 3.300 V，可填写实测值。'}):field('触发方式','trigger',p.trigger,{full:true,choices:[['none','立即采集'],['rising','上升沿'],['falling','下降沿'],['high','高电平'],['low','低电平']]})+field('触发通道','trigger_channel',p.trigger_channel,{full:true,choices:Array.from({length:8},(_,i)=>[i,`D${i} · GP${20+i}`])})}${field('等待超时 / s','timeout',p.timeout,{full:true})}</div><div class="buttons">${button(op,true)}</div><div class="help-box">${analog?'单次采集，先存入板上 RAM 再传输。12 bit 为 ADC 码宽，电压未经校准；500 kSa/s 是采样率，不是模拟带宽。本版不含连续流或硬件模拟触发。':'8 通道同时采集；单级触发、无前触发样本。最高 20 MSa/s 为本版配置上限，信号质量与最高可用速度仍需真机验证。'}</div></div></section><section class="panel wave-panel"><div class="panel-header"><h2>${analog?'模拟波形':'数字波形'}</h2><span class="pill">${state.demo?'DEMO':cap?'CAPTURED':'READY'}</span></div><div class="panel-body"><div class="wave-tools"><div class="wave-controls"><button id="wave-zoom-in" class="small" title="放大时间轴">＋ 放大</button><button id="wave-zoom-out" class="small" title="缩小时间轴">− 缩小</button><button id="wave-reset" class="small">显示全部</button><label>窗口 <select id="wave-window" aria-label="波形窗口点数"><option value="all">全部样本</option>${[4096,1024,256,64,32].map(n=>`<option value="${n}">${n.toLocaleString()} 点</option>`).join('')}<option value="custom" hidden>自定义</option></select></label></div><span id="wave-caption">${cap?`${rateLabel(cap.rate)} · ${cap.count.toLocaleString()} 点`:'采集后显示波形'}</span></div><canvas id="waveform" class="waveform" tabindex="0" aria-label="${analog?'ADC 电压随时间变化':'8 通道数字信号波形'}" aria-describedby="wave-help"></canvas><div class="wave-position"><label for="wave-offset">时间位置</label><output id="wave-position">等待采集数据</output></div><input id="wave-offset" aria-label="移动波形窗口" aria-describedby="wave-pan-hint" type="range" min="0" max="0" value="0" step="1" disabled><p id="wave-pan-hint" class="wave-pan-hint">采集完成后可缩放与平移。</p><div class="cursor-readout" id="cursor-readout">点击波形设置 A / B 游标，测量时间差${analog?'与电压差':''}。</div><small class="subtle" id="wave-help">滚轮缩放时间轴，放大后拖动波形或下方滑杆平移；单击设置 A / B 游标。聚焦波形后可用 + / − 缩放、← / → 平移、Home 显示全部。全景保留像素内最小/最大值，线段连接仅用于显示。</small>${cap&&analog?`<div class="measurement-grid">${[['最低',result.measurements.min_v],['最高',result.measurements.max_v],['峰峰值',result.measurements.vpp],['均值',result.measurements.mean_v],['RMS',result.measurements.rms_v]].map(([k,v])=>`<div><small>${k}</small><b>${v.toFixed(4)} <em>V</em></b></div>`).join('')}</div><p class="subtle">达到量程边界的采样点：${result.measurements.clipped} · 未校准电压</p>`:''}<div class="buttons">${(result?.downloads||[]).map(f=>`<button data-capture-file="${escapeHTML(f.id)}">导出 ${escapeHTML(f.name.split('.').pop().toUpperCase())} ↓</button>`).join('')}${cap&&state.demo?'<span class="subtle">演示数据可随任务 JSON 导出</span>':''}</div></div></section></div><div style="margin-top:22px">${output()}</div>`;
}

let releaseInstrument = () => {};
export function bindInstrument(state){
 releaseInstrument();
 const canvas=document.querySelector('#waveform');if(!canvas)return;
 const analog=state.page==='scope',job=state.activeJob?.op===(analog?'scope.capture':'logic.capture')?state.activeJob:null,result=job?.result;
 const cap=result?.capture;let samples=[];
 if(cap&&result.samples_b64){const raw=Uint8Array.from(atob(result.samples_b64),c=>c.charCodeAt(0));samples=analog?Array.from({length:raw.length/2},(_,i)=>raw[i*2]|raw[i*2+1]<<8):raw}
 const total=samples.length, views=state.waveViews??(state.waveViews={});
 // Keep the view when the page rerenders; a new capture starts at full extent.
 if(views[state.page]?.jobId!==job?.id||views[state.page]?.total!==total)views[state.page]={jobId:job?.id,total,...normalizeView(total),cursors:[],nextCursor:0};
 const view=views[state.page], range=document.querySelector('#wave-offset'), select=document.querySelector('#wave-window');
 const zoomIn=document.querySelector('#wave-zoom-in'),zoomOut=document.querySelector('#wave-zoom-out'),reset=document.querySelector('#wave-reset');
 const left=72,right=18,top=28,bottom=30;
 const fraction=e=>Math.max(0,Math.min(1,(e.clientX-canvas.getBoundingClientRect().left-left)/Math.max(1,canvas.clientWidth-left-right)));
 const readCursors=()=>{
  const [a,b]=view.cursors;
  if(a===undefined&&b===undefined)return;
  let text=`A ${a===undefined?'—':formatTime(a/cap.rate,1/cap.rate)} · B ${b===undefined?'—':formatTime(b/cap.rate,1/cap.rate)}`;
  if(a!==undefined&&b!==undefined){const delta=Math.abs(b-a)/cap.rate;text+=` · Δt ${(delta*1e6).toFixed(3)} µs`;if(delta)text+=` · 1/Δt ${(1/delta).toFixed(1)} Hz`;if(analog)text+=` · ΔV ${((samples[b]-samples[a])*cap.vref/4096).toFixed(4)} V`}
  document.querySelector('#cursor-readout').textContent=text;
 };
 const draw=()=>{
  const {start,size}=view,width=canvas.clientWidth||600,height=analog?330:378,dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(width*dpr);canvas.height=height*dpr;canvas.style.height=height+'px';const c=canvas.getContext('2d');c.scale(dpr,dpr);
  c.fillStyle='#102925';c.fillRect(0,0,width,height);const w=Math.max(1,width-left-right),h=height-top-bottom;
  c.font='11px ui-monospace, monospace';
  for(let i=0;i<=10;i++){const x=left+w*i/10;c.strokeStyle='#24423a';c.beginPath();c.moveTo(x,top);c.lineTo(x,height-bottom);c.stroke();if(i%2===0){c.fillStyle='#9eb7aa';c.textAlign=i===0?'left':i===10?'right':'center';c.fillText(total?formatTime((start+(size-1)*i/10)/cap.rate,(size-1)/cap.rate/10):'—',x,height-10)}}
  c.textAlign='left';
  for(let row=0;row<(analog?5:8);row++){const y=top+(analog?row*h/4:row*h/8);c.strokeStyle='#24423a';c.beginPath();c.moveTo(left,y);c.lineTo(width-right,y);c.stroke();c.fillStyle='#a6c2b2';c.fillText(analog?((cap?.vref||3.3)*(1-row/4)).toFixed(2)+' V':`D${row} GP${20+row}`,8,analog?y+4:y+18)}
  if(!total){c.fillStyle='#7d9c8c';c.textAlign='center';c.fillText('等待采集数据',left+w/2,top+h/2);return}
  const end=start+size;
  c.save();c.beginPath();c.rect(left,top,w,h);c.clip();
  for(let ch=0;ch<(analog?1:8);ch++){
   c.strokeStyle=analog?'#bbde85':['#bbe0a2','#6bd0c3','#dfc382','#b29ede','#7cb9d6','#de9d8b','#94c583','#d7acbf'][ch];c.lineWidth=1.3;c.beginPath();
   const y=v=>analog?top+h*(1-v/4096):top+ch*h/8+27-v*20;
   if(size<=w){
    // At close zoom each sample has its own position; connect analog samples,
    // and preserve digital steps instead of drawing diagonal logic edges.
    let prev=null;
    for(let i=start;i<end;i++){const x=left+(i-start)/Math.max(1,size-1)*w,v=y(analog?samples[i]:(samples[i]>>ch)&1);if(prev===null)c.moveTo(x,v);else {if(!analog)c.lineTo(x,prev);c.lineTo(x,v)}prev=v}
   }else{
    let prev=null;
    for(let px=0;px<Math.ceil(w);px++){
     const a=start+Math.floor(px*size/w),b=Math.min(end,start+Math.max(Math.floor(px*size/w)+1,Math.floor((px+1)*size/w)));let lo=Infinity,hi=-Infinity;
     for(let i=a;i<b;i++){const v=analog?samples[i]:((samples[i]>>ch)&1);lo=Math.min(lo,v);hi=Math.max(hi,v)}
     const x=left+px,ylo=y(lo),yhi=y(hi);if(prev!==null){c.moveTo(x-1,prev);c.lineTo(x,ylo)}c.moveTo(x,ylo);c.lineTo(x,yhi);prev=yhi;
    }
   }c.stroke();
  }
  c.restore();
  view.cursors.forEach((index,i)=>{if(index<start||index>=end)return;const x=left+(index-start)/Math.max(1,size-1)*w;c.strokeStyle=i?'#e6b08e':'#e4e9cb';c.setLineDash([4,4]);c.beginPath();c.moveTo(x,top);c.lineTo(x,height-bottom);c.stroke();c.setLineDash([]);c.fillStyle=c.strokeStyle;c.fillText(i?'B':'A',Math.min(x+4,width-14),18)});
 };
 const sync=()=>{
  const {start,size}=view,max=total-size;
  range.max=max;range.value=start;range.disabled=!total||max===0;
  range.setAttribute('aria-valuetext',total?`第 ${start+1} 至 ${start+size} 点，共 ${total} 点`:'等待采集数据');
  select.disabled=!total;zoomIn.disabled=!total||size<=Math.min(total,MIN_WINDOW);zoomOut.disabled=reset.disabled=!total||size===total;
  for(const option of select.options)if(!['all','custom'].includes(option.value))option.disabled=+option.value>total;
  const value=size===total?'all':Array.from(select.options).some(o=>o.value===String(size))?String(size):'custom';
  const custom=select.querySelector('[value="custom"]');custom.hidden=value!=='custom';custom.textContent=`${size.toLocaleString()} 点`;select.value=value;
  canvas.classList.toggle('can-pan',max>0);canvas.classList.toggle('has-samples',total>0);
  document.querySelector('#wave-caption').textContent=total?`${(cap.rate/1000).toLocaleString()} kSa/s · ${(total/size).toFixed(1)}×`:'采集后显示波形';
  document.querySelector('#wave-position').textContent=total?`${(start+1).toLocaleString()}–${(start+size).toLocaleString()} / ${total.toLocaleString()} 点 · ${formatTime(start/cap.rate,1/cap.rate)}–${formatTime((start+size-1)/cap.rate,1/cap.rate)}`:'等待采集数据';
  document.querySelector('#wave-pan-hint').textContent=!total?'请先采集波形，完成后可缩放与平移。':max===0?'当前显示全部样本；点击“＋ 放大”或向上滚动，滑杆即可移动。':'拖动滑杆或波形查看前后数据；滑杆聚焦后可用方向键微调。';
  readCursors();draw();
 };
 const setView=next=>{Object.assign(view,normalizeView(total,next));sync()};
 const zoom=(factor,anchor=0.5)=>setView(resizeView(total,view,view.size*factor,anchor));
 select.onchange=()=>{if(select.value!=='custom')setView(resizeView(total,view,select.value==='all'?total:+select.value))};
 range.oninput=()=>setView({start:+range.value,size:view.size});
 zoomIn.onclick=()=>zoom(0.5);zoomOut.onclick=()=>zoom(2);reset.onclick=()=>setView({start:0,size:total});
 canvas.addEventListener('wheel',e=>{if(!total||!e.deltaY)return;e.preventDefault();zoom(e.deltaY<0?0.5:2,fraction(e))},{passive:false});
 let drag=null;
 canvas.onpointerdown=e=>{if(!total||e.button!==0||drag)return;const r=canvas.getBoundingClientRect();if(e.clientX<r.left+left||e.clientX>r.right-right||e.clientY<r.top+top||e.clientY>r.bottom-bottom)return;canvas.focus({preventScroll:true});drag={id:e.pointerId,x:e.clientX,y:e.clientY,start:view.start,moved:false};canvas.setPointerCapture(e.pointerId)};
 canvas.onpointermove=e=>{if(!drag||drag.id!==e.pointerId)return;const dx=e.clientX-drag.x;if(Math.hypot(dx,e.clientY-drag.y)>4)drag.moved=true;if(drag.moved){canvas.classList.add('dragging');setView({start:drag.start-Math.round(dx/Math.max(1,canvas.clientWidth-left-right)*(view.size-1)),size:view.size})}};
 const endDrag=e=>{if(!drag||drag.id!==e.pointerId)return;const click=!drag.moved&&e.type==='pointerup';drag=null;canvas.classList.remove('dragging');if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);if(click){view.cursors[view.nextCursor]=Math.min(total-1,view.start+Math.round(fraction(e)*(view.size-1)));view.nextCursor=1-view.nextCursor;readCursors();draw()}};
 canvas.onpointerup=endDrag;canvas.onpointercancel=endDrag;canvas.onlostpointercapture=()=>{drag=null;canvas.classList.remove('dragging')};
 canvas.onkeydown=e=>{if(!total||e.ctrlKey||e.metaKey||e.altKey)return;if(['+','=','-','ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();if(e.key==='+'||e.key==='=')zoom(0.5);else if(e.key==='-')zoom(2);else if(e.key==='Home')setView({start:0,size:total});else setView({start:view.start+(e.key==='ArrowLeft'?-1:1)*Math.max(1,Math.round(view.size/10)),size:view.size})}};
 const observer=new ResizeObserver(draw);observer.observe(canvas);releaseInstrument=()=>observer.disconnect();
 sync();
}
export function demoCapture(analog,p){
 const n=+p.samples,rate=+p.rate;let bytes,samples;
 if(analog){samples=Array.from({length:n},(_,i)=>Math.round(2048+1350*Math.sin(2*Math.PI*1000*i/rate)+40*Math.sin(i*1.17)));bytes=new Uint8Array(n*2);samples.forEach((v,i)=>{bytes[2*i]=v&255;bytes[2*i+1]=v>>8})}
 else{samples=Array.from({length:n},(_,i)=>[7,19,37,83,151,293,503,997].reduce((v,k,ch)=>v|((Math.floor(i/k)%2)<<ch),0));bytes=Uint8Array.from(samples)}
 let binary='';for(const b of bytes)binary+=String.fromCharCode(b);
 const result={source:'DEMO',capture:{rate,count:n,channels:analog?1:8,channel:+p.channel||0,gpio_base:analog?26+(+p.channel||0):20,vref:+p.vref||3.3,bits:analog?12:1},samples_b64:btoa(binary),downloads:[]};
 if(analog){let volts=samples.map(x=>x*result.capture.vref/4096),min=Math.min(...volts),max=Math.max(...volts);result.measurements={min_v:min,max_v:max,vpp:max-min,mean_v:volts.reduce((a,b)=>a+b,0)/n,rms_v:Math.sqrt(volts.reduce((a,b)=>a+b*b,0)/n),clipped:0}}
 return result;
}
