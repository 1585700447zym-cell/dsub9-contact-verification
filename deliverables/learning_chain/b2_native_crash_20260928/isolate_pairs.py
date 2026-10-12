import json
from pathlib import Path
import subprocess
import sys
from probe import HERE,ROOT,write

pairs=json.loads((HERE/'pair_scan/pairs.json').read_text())
history=[]
def run(group,name):
    mode='subset_'+name
    write(HERE/(mode+'.json'),group)
    with (HERE/(name+'.log')).open('x',encoding='utf-8') as log:
        p=subprocess.run([sys.executable,'-X','utf8','-X','faulthandler','-B',str(HERE/'replay.py'),
            '--worker',mode,str(HERE/name)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    row=dict(name=name,pairs=len(group),returncode=p.returncode,hex=hex(p.returncode&0xffffffff))
    history.append(row);write(HERE/'pair_isolation.json',history);print(row,flush=True)
    if p.returncode not in (0,3221225477,-1073741819):raise RuntimeError('Unexpected failure')
    return p.returncode!=0

for level in range(12):
    if len(pairs)==1:break
    cut=len(pairs)//2
    if run(pairs[:cut],f'bisect_{level:02d}_a'):
        pairs=pairs[:cut]
    elif run(pairs[cut:],f'bisect_{level:02d}_b'):
        pairs=pairs[cut:]
    else:
        write(HERE/'pair_interaction.json',dict(remaining_pairs=pairs,level=level,reason='Both subsets pass; batch interaction or filtering difference'))
        break
write(HERE/'isolated_pairs.json',pairs)
