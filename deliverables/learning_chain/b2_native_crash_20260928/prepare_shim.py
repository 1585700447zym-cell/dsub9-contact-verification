import struct,subprocess
from pathlib import Path
from probe import HERE,ROOT
# Only the unused libccd vector type appears in these native CCD header prototypes.
p=HERE/'diagnostic_include/ccd/vec3.h';p.parent.mkdir(parents=True,exist_ok=True)
p.write_text('typedef struct { double v[3]; } ccd_vec3_t;\n',encoding='utf-8')
source=(HERE/'upstream/engine_collision_gjk.c').read_text()
guard='''
  if (pt->horizon.nedges >= 24) {
    fprintf(stderr, "HORIZON_OVERFLOW nedges=%d allocated=24 nfaces=%d nverts=%d\\n", pt->horizon.nedges,pt->nfaces,pt->nverts);
    fflush(stderr); exit(86);
  }
'''
needle='static inline void addEdge(Polytope* pt, int index, int edge) {'
assert source.count(needle)==1
(HERE/'engine_collision_gjk_guard.c').write_text('#include <stdio.h>\n'+source.replace(needle,needle+guard),encoding='utf-8')
b=(ROOT/'tmp/mujoco_3_13_probe/mujoco/mujoco.dll').read_bytes()
u16=lambda x:struct.unpack_from('<H',b,x)[0];u32=lambda x:struct.unpack_from('<I',b,x)[0]
pe=u32(0x3c);opt=pe+24;sections=[]
for i in range(u16(pe+6)):
 p=opt+u16(pe+20)+40*i;vs,va,rs,ro=struct.unpack_from('<IIII',b,p+8);sections.append((va,max(vs,rs),ro))
def off(rva):
 for va,size,ro in sections:
  if va<=rva<va+size:return ro+rva-va
 raise ValueError(rva)
e=off(u32(opt+112));nn=u32(e+24);an=u32(e+32);names=[]
for i in range(nn):
 p=off(u32(off(an)+4*i));names.append(b[p:b.index(b'\0',p)].decode())
(HERE/'mujoco.def').write_text('LIBRARY mujoco.dll\nEXPORTS\n'+'\n'.join(names)+'\n')
lib=Path('D:/software/vs chanpin/VC/Tools/MSVC/14.51.36231/bin/Hostx64/x64/lib.exe')
subprocess.run([str(lib),'/nologo','/machine:x64','/def:'+str(HERE/'mujoco.def'),'/out:'+str(HERE/'mujoco_import.lib')],check=True)
