"""Copy original bound sources before claiming the finite physical run."""
from pathlib import Path
import shutil
from tools.learning.v4_pilot_contract import ROOT,read,sha
from tools.validation.run_v4_learning_pilot import PilotAdmission
from tools.validation.run_clearance_preflight import write
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
OUT=Path(__file__).resolve().parent
pin=read(OUT/'qualification_pin.json')['sha256'];admission=PilotAdmission(OUT,pin)
for mode in ('F50','S50'):admission.verify(mode)
cfg=read(OUT/'configuration.json');paths={**cfg['common']['frozen_common_source_sha256'],**cfg['input_sha256']}
for name,digest in paths.items():
    assert sha(ROOT/name)==digest,name
    dest=OUT/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():raise FileExistsError(dest)
    shutil.copy2(ROOT/name,dest);assert sha(dest)==digest
write(OUT/'execution_source_binding.json',dict(qualification_sha256=pin,files=paths))
print('frozen bound inputs',len(paths))
