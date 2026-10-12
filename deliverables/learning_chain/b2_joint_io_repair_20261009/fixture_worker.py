"""Standard-library child fixture: files and sleeping processes only."""
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from supervised import enter_gate
from joint_contract import write

mode,folder,gate,pid,registered=sys.argv[1:]
folder=Path(folder)
enter_gate(gate,pid,registered)
phase=dict(started=time.time(),limit_s=1200,kind='physical',id='file_test')
if mode=='invalid':phase['kind']='unknown'
if mode=='expired':phase['started']-=1201
if mode=='future':phase['started']+=10000
if mode=='malformed':
    (folder/'phase.json').write_text('{broken',encoding='utf8')
else:write(folder/'phase.json',phase)
if mode=='fast_corrupt':
    time.sleep(.03)
    (folder/'phase.json').write_text('{broken',encoding='utf8')
    sys.exit(0)
if mode=='fail':raise RuntimeError('Intentional child error')
if mode=='hang':
    subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(20)'],creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(20)
elif mode=='locked':
    time.sleep(.06)
    from test_io_repair import exclusive
    release=exclusive(folder/'phase.json')
    time.sleep(2);release()
else:time.sleep(.15)
