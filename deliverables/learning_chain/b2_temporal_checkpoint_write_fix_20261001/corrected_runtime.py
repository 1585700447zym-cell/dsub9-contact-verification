"""Drop-in Branch writer correction; no execution permit or launch on import.

The frozen failed run remains byte-for-byte unchanged. A future execution must
bind this corrected producer explicitly under its own authority and budget.
"""
import json,os,sys,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=ROOT/'deliverables/learning_chain/b2_temporal_learning_validation_20261001'
sys.path.insert(0,str(OLD))
import learning_runtime as original
import torch
from tools.learning.sac_checkpoint import _flush_write

class Branch(original.Branch):
    def save(self,path):
        path=Path(path)
        if path.exists():raise FileExistsError('Checkpoint already exists')
        state=self.capture() # Original healthy boundary/source/data validation.
        path.parent.mkdir(parents=True,exist_ok=True)
        staging=path.with_name(path.name+'.staging-'+uuid.uuid4().hex);staging.mkdir()
        # torch.save owns serialization; flush helper accepts bytes, not callbacks.
        with (staging/'state.pt').open('xb') as stream:
            torch.save(state,stream);stream.flush();os.fsync(stream.fileno())
        manifest=dict(version='temporal_checkpoint_manifest_v1',arm=state['arm'],binding_sha256=state['binding_sha256'],
            authorization_sha256=state['authorization_sha256'],state_sha256=original.C.digest(staging/'state.pt'),
            batches=len(state['history']),dataset_sha256=state['dataset_sha256'])
        _flush_write(staging/'manifest.json',json.dumps(manifest,sort_keys=True,allow_nan=False,indent=2).encode('utf-8'))
        if path.exists():raise FileExistsError('Checkpoint already exists')
        os.rename(staging,path);return original.C.digest(path/'manifest.json')
