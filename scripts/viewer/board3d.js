import {softwareRenderer} from './software3d.js';
import {Scene,Color,PerspectiveCamera,WebGLRenderer,HemisphereLight,DirectionalLight,Box3,Vector3,SRGBColorSpace,ACESFilmicToneMapping} from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
export function mountBoard3D(host,url,fallback){
 let disposed=false,model=null,renderer,controls,observer;
 const disposeModel=root=>root?.traverse(o=>{o.geometry?.dispose();for(const m of (Array.isArray(o.material)?o.material:[o.material])){if(!m)continue;for(const v of Object.values(m))if(v?.isTexture)v.dispose();m.dispose();}});
 try{renderer=new WebGLRenderer({antialias:true,alpha:false});}catch(e){renderer=softwareRenderer();host.dataset.renderer='canvas';}
 renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=SRGBColorSpace;renderer.toneMapping=ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
 renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label','可拖动旋转的板卡三维模型');host.append(renderer.domElement);
 const scene=new Scene();scene.background=new Color('#f2f6f3');const camera=new PerspectiveCamera(35,1,.1,10000);
 scene.add(new HemisphereLight(0xffffff,0x768779,3));for(const [x,y,z,power] of [[20,50,30,3],[-40,20,-30,2],[30,-40,10,1.5]]){const l=new DirectionalLight(0xffffff,power);l.position.set(x,y,z);scene.add(l);}
 controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;controls.minDistance=12;controls.maxDistance=250;controls.listenToKeyEvents(renderer.domElement);
 const draw=()=>{if(!disposed){renderer.render(scene,camera);host.dataset.camera=camera.position.toArray().map(n=>n.toFixed(2)).join(',');}};
 const size=()=>{const w=host.clientWidth,h=host.clientHeight;camera.aspect=w/Math.max(1,h);camera.updateProjectionMatrix();renderer.setSize(w,h,false);draw();};
 const reset=()=>{controls.target.set(0,0,0);camera.position.set(8,48,36);controls.update();draw();};
 const zoom=factor=>{camera.position.sub(controls.target).multiplyScalar(factor).clampLength(12,250).add(controls.target);controls.update();draw();};
 controls.addEventListener('change',draw);observer=new ResizeObserver(size);observer.observe(host);reset();size();
 document.querySelectorAll('[data-cad-face]').forEach(b=>b.onclick=()=>{controls.target.set(0,0,0);const sign=b.dataset.cadFace==='top'?1:-1;camera.position.set(0,sign*52,sign*.001);controls.update();draw();});
 document.querySelector('[data-cad-reset]').onclick=reset;document.querySelector('[data-cad-zoom="in"]').onclick=()=>zoom(.8);document.querySelector('[data-cad-zoom="out"]').onclick=()=>zoom(1.25);
 new GLTFLoader().load(url,gltf=>{if(disposed){disposeModel(gltf.scene);return;}model=gltf.scene;model.scale.setScalar(1000);const box=new Box3().setFromObject(model);model.position.sub(box.getCenter(new Vector3()));scene.add(model);host.querySelector('.cad-loading')?.remove();host.dataset.loaded='true';if(host.dataset.renderer==='canvas'){const label=document.createElement('span');label.className='cad-renderer-label';label.textContent='兼容渲染 · 原始 GLB 几何';host.append(label);}draw();},undefined,()=>{if(!disposed){host.querySelector('.cad-loading').textContent='三维模型加载失败，请下载 GLB 或切换 PCB 视图。';}});
 return ()=>{disposed=true;observer.disconnect();controls.dispose();disposeModel(model);renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();};
}
