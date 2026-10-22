// Canvas 2D fallback: projects the actual GLB triangles. No WebGL or external service.
import {Matrix4,Vector3,Color} from 'three';
export function softwareRenderer(){
 const domElement=document.createElement('canvas'),ctx=domElement.getContext('2d');if(!ctx)throw Error('浏览器不支持 Canvas');
 let width=1,height=1,ratio=1,cachedRoot=null,meshes=[],triangles=[],queued=false,lastScene,lastCamera,disposed=false;
 const light=new Vector3(-.3,.8,.5).normalize();
 const cache=scene=>{const root=scene.children.find(o=>o.type==='Group');if(root===cachedRoot)return;cachedRoot=root;meshes=[];triangles=[];scene.updateMatrixWorld(true);
  root?.traverse(o=>{if(!o.isMesh||!o.geometry.attributes.position)return;const a=o.geometry.attributes.position,vertices=new Float32Array(a.count*3),v=new Vector3();for(let i=0;i<a.count;i++){v.fromBufferAttribute(a,i).applyMatrix4(o.matrixWorld);vertices.set(v.toArray(),i*3);}const mesh={vertices,screen:new Float32Array(a.count*3)};meshes.push(mesh);const indices=o.geometry.index?.array, count=indices?.length||a.count;
   const material=Array.isArray(o.material)?o.material[0]:o.material,c=material?.color?.clone()||new Color('#627b65');c.convertLinearToSRGB();const va=new Vector3(),vb=new Vector3(),vc=new Vector3(),normal=new Vector3();
   for(let i=0;i+2<count;i+=3){const ia=(indices?indices[i]:i)*3,ib=(indices?indices[i+1]:i+1)*3,ic=(indices?indices[i+2]:i+2)*3;va.fromArray(vertices,ia);vb.fromArray(vertices,ib);vc.fromArray(vertices,ic);normal.subVectors(vb,va).cross(vc.sub(va)).normalize();const shade=.55+.45*Math.abs(normal.dot(light));triangles.push({mesh,a:ia,b:ib,c:ic,z:0,color:[Math.round(c.r*255*shade),Math.round(c.g*255*shade),Math.round(c.b*255*shade)],alpha:material?.opacity??1});}
  });
 };
 const draw=()=>{queued=false;if(disposed)return;const scene=lastScene,camera=lastCamera;cache(scene);camera.updateMatrixWorld();const matrix=new Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse).elements;
  for(const m of meshes){const v=m.vertices,s=m.screen;for(let i=0;i<v.length;i+=3){const x=v[i],y=v[i+1],z=v[i+2],w=matrix[3]*x+matrix[7]*y+matrix[11]*z+matrix[15];s[i]=((matrix[0]*x+matrix[4]*y+matrix[8]*z+matrix[12])/w*.5+.5)*width;s[i+1]=(-(matrix[1]*x+matrix[5]*y+matrix[9]*z+matrix[13])/w*.5+.5)*height;s[i+2]=(matrix[2]*x+matrix[6]*y+matrix[10]*z+matrix[14])/w;}}
  for(const t of triangles){const s=t.mesh.screen;t.z=(s[t.a+2]+s[t.b+2]+s[t.c+2])/3;}triangles.sort((a,b)=>b.z-a.z);
  const frame=ctx.createImageData(width,height),pixels=frame.data,depth=new Float32Array(width*height).fill(Infinity);
  for(let i=0;i<pixels.length;i+=4){pixels[i]=242;pixels[i+1]=246;pixels[i+2]=243;pixels[i+3]=255;}
  for(const t of triangles){if(t.z<-1||t.z>1)continue;const s=t.mesh.screen,ax=s[t.a],ay=s[t.a+1],bx=s[t.b],by=s[t.b+1],cx=s[t.c],cy=s[t.c+1],den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy);if(Math.abs(den)<.01)continue;
   const x0=Math.max(0,Math.floor(Math.min(ax,bx,cx))),x1=Math.min(width-1,Math.ceil(Math.max(ax,bx,cx))),y0=Math.max(0,Math.floor(Math.min(ay,by,cy))),y1=Math.min(height-1,Math.ceil(Math.max(ay,by,cy)));
   for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){const u=((by-cy)*(x+.5-cx)+(cx-bx)*(y+.5-cy))/den,v=((cy-ay)*(x+.5-cx)+(ax-cx)*(y+.5-cy))/den,w=1-u-v;if(u<0||v<0||w<0)continue;const z=u*s[t.a+2]+v*s[t.b+2]+w*s[t.c+2],index=y*width+x;if(z>depth[index]+1e-7)continue;depth[index]=z;const off=index*4;for(let k=0;k<3;k++)pixels[off+k]=t.color[k]*t.alpha+pixels[off+k]*(1-t.alpha);}
  }
  ctx.putImageData(frame,0,0);
 };
 return {domElement,setPixelRatio(r){ratio=1;},setSize(w,h){width=Math.round(w);height=Math.round(h);domElement.width=Math.round(w*ratio);domElement.height=Math.round(h*ratio);},render(scene,camera){lastScene=scene;lastCamera=camera;if(!queued&&!disposed){queued=true;requestAnimationFrame(draw);}},dispose(){disposed=true;meshes=[];triangles=[];},forceContextLoss(){}};
}
