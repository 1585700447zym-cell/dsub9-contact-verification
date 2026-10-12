import hashlib,json,re,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
out=HERE/'upstream'
queue=['src/engine/engine_collision_gjk.h','src/engine/engine_collision_convex.h',
       'src/engine/engine_util_blas.h','src/engine/engine_util_errmem.h','include/mujoco/mujoco.h']
done={}
while queue:
    name=queue.pop(0)
    if name in done:continue
    if len(done)>100:raise RuntimeError('Unexpected header dependency count')
    path=out/name
    if path.exists(): data=path.read_bytes()
    else:
        print(name,flush=True)
        data=urllib.request.urlopen('https://raw.githubusercontent.com/google-deepmind/mujoco/3.13.0/'+name,timeout=20).read()
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    done[name]=hashlib.sha256(data).hexdigest()
    for prefix,dep in re.findall(r'#include\s*[<"]((mujoco|engine)/[^">]+)[">]',data.decode()):
        queue.append(('include/' if dep=='mujoco' else 'src/')+prefix)
(out/'header_sources.json').write_text(json.dumps(done,indent=2),encoding='utf-8')
print('Downloaded',len(done),'version-pinned headers')
