"""Convert KiCad's embedded VRML export to GLB, retaining silk and material colors.
Build-time only: requires numpy. Supports the exact VRML nodes emitted by KiCad 9.
"""
import json, re, struct, sys
from pathlib import Path
import numpy as np

class Parser:
    def __init__(self,text):
        self.tokens=re.findall(r'"[^"\n]*"|[{}\[\]]|[^\s,{}\[\]]+',re.sub(r'#[^\n]*','',text));self.i=0;self.defs={}
    def pop(self):
        t=self.tokens[self.i];self.i+=1;return t
    def value(self):
        t=self.pop()
        if t=='DEF':
            name=self.pop();v=self.value();self.defs[name]=v;return v
        if t=='USE':return self.defs[self.pop()]
        if t=='[':
            a=[]
            while self.tokens[self.i]!=']':a.append(self.value())
            self.pop();return a
        if self.i<len(self.tokens) and self.tokens[self.i]=='{':
            self.pop();d={'type':t}
            while self.tokens[self.i]!='}':
                key=self.pop();n={'center':3,'translation':3,'scale':3,'diffuseColor':3,'emissiveColor':3,'specularColor':3,'rotation':4,'scaleOrientation':4}.get(key,1)
                d[key]=[self.value() for _ in range(n)] if n>1 else self.value()
            self.pop();return d
        if t in ('TRUE','FALSE'):return t=='TRUE'
        try:return float(t)
        except ValueError:return t

def rot(v):
    x,y,z,a=v;c=np.cos(a);s=np.sin(a);q=1-c
    m=np.eye(4);m[:3,:3]=[[c+x*x*q,x*y*q-z*s,x*z*q+y*s],[y*x*q+z*s,c+y*y*q,y*z*q-x*s],[z*x*q-y*s,z*y*q+x*s,c+z*z*q]];return m

def translation(v):
    m=np.eye(4);m[:3,3]=v;return m

def convert(src,dest):
    parser=Parser(Path(src).read_text());roots=[]
    while parser.i<len(parser.tokens):roots.append(parser.value())
    groups={};axis=np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float)
    def walk(n,parent):
        if n['type']=='Transform':
            c=n.get('center',[0,0,0]);so=rot(n.get('scaleOrientation',[0,0,1,0]));m=parent@translation(n.get('translation',[0,0,0]))@translation(c)@rot(n.get('rotation',[0,0,1,0]))@so@np.diag(n.get('scale',[1,1,1])+[1])@np.linalg.inv(so)@translation([-v for v in c])
            for child in n.get('children',[]):walk(child,m)
        elif n['type']=='Shape':
            geom=n['geometry'];assert geom['type']=='IndexedFaceSet'
            mat=n['appearance']['material'];color=mat.get('diffuseColor',[.7,.7,.7]);alpha=1-mat.get('transparency',0);key=tuple(color+[alpha,mat.get('shininess',.2)])
            verts=np.array(geom['coord']['point']).reshape(-1,3);world=(parent@np.c_[verts,np.ones(len(verts))].T).T[:,:3];norms=np.array(geom['normal']['vector']).reshape(-1,3)@np.linalg.inv(parent[:3,:3]);norms/=np.maximum(np.linalg.norm(norms,axis=1,keepdims=True),1e-12)
            faces=[];face=[]
            for index in geom['coordIndex']:
                if index==-1:
                    for j in range(1,len(face)-1):faces.extend([face[0],face[j],face[j+1]])
                    face=[]
                else:face.append(int(index))
            assert not face and len(norms)==len(world)
            groups.setdefault(key,[]).append((world,norms,np.array(faces,dtype=np.uint32)))
        else:raise ValueError('Unsupported node '+n['type'])
    for root in roots:walk(root,axis)
    doc={'asset':{'version':'2.0','generator':'Debug Studio / KiCad 9 VRML materials'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0,'name':'KiCad board and original silkscreen'}],'meshes':[{'primitives':[]}],'materials':[],'accessors':[],'bufferViews':[],'buffers':[]};binary=bytearray()
    def accessor(a,kind,component):
        a=np.ascontiguousarray(a,dtype='<f4' if component==5126 else '<u4');offset=len(binary);binary.extend(a.tobytes());binary.extend(b'\0'*((-len(binary))%4));view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':a.nbytes});entry={'bufferView':view,'componentType':component,'count':len(a),'type':kind}
        if kind=='VEC3':entry.update(min=a.min(axis=0).tolist(),max=a.max(axis=0).tolist())
        doc['accessors'].append(entry);return len(doc['accessors'])-1
    for key,parts in groups.items():
        positions=[];normals=[];indices=[];offset=0
        for v,n,i in parts:positions.append(v);normals.append(n);indices.append(i+offset);offset+=len(v)
        rgb=np.array(key[:3]);linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        mat={'name':'KiCad VRML material','pbrMetallicRoughness':{'baseColorFactor':linear.tolist()+[key[3]],'metallicFactor':.45 if key[4]>.5 else .05,'roughnessFactor':max(.18,1-key[4])},'doubleSided':True}
        if key[3]<1:mat['alphaMode']='BLEND'
        doc['materials'].append(mat);doc['meshes'][0]['primitives'].append({'attributes':{'POSITION':accessor(np.concatenate(positions),'VEC3',5126),'NORMAL':accessor(np.concatenate(normals),'VEC3',5126)},'indices':accessor(np.concatenate(indices),'SCALAR',5125),'material':len(doc['materials'])-1,'mode':4})
    doc['buffers']=[{'byteLength':len(binary)}];raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4);data=struct.pack('<4sII',b'glTF',2,28+len(raw)+len(binary))+struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(binary),b'BIN\0')+binary;Path(dest).write_bytes(data);print(f'{dest}: {len(data)} bytes, {len(groups)} materials')
if __name__=='__main__':convert(sys.argv[1],sys.argv[2])
