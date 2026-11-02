"""Four deterministic development episodes with an isolated, nonlearning sink."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
from .contact_execution import ContactCollector
from .contact_contract import POINTS
from .audited_replay import AuditedReplay
from .admitted_collection import _write_json
from .engineering_evaluation import EvaluationCollector,FrozenPolicy,episode_metrics
from .sac_checkpoint import capture,_same


def evaluation_cases():
    return [dict(name=name,x_offset_m=x,y_offset_m=y,roll_rad=0.,pitch_rad=0.,start_origin_z_m=-.004,target_depth_m=.004)
            for name,(x,y) in zip(('x_neg_100','x_pos_100','y_neg_100','y_pos_100'),POINTS)]


class ContactEvaluationCollector(ContactCollector):
    def __init__(self,*,admission,output,checkpoint_sha256,updater):
        self.method='sac'; self.checkpoint_sha256=checkpoint_sha256
        super().__init__(admission=admission,output=output,updater=updater,replay=AuditedReplay(capacity=100000))
    def start(self,episode_id,*,case,seed):
        super().start(episode_id,case=case,seed=seed)
        # Legacy evaluation archiver expects the full counter map.
        self._start_count=deepcopy(self.updater.counts)
    def collect(self,policy,steps,*,cut_at_end=False,deterministic=True):
        if type(policy) is not FrozenPolicy or policy.updater is not self.updater or deterministic is not True:
            raise ValueError('Frozen deterministic selected policy required')
        return super().collect(policy,steps,cut_at_end=cut_at_end,deterministic=True)
    def retry_publication(self):
        return EvaluationCollector.retry_publication(self)


def evaluate(chain,*,checkpoint_sha256,output):
    if not isinstance(checkpoint_sha256,str) or len(checkpoint_sha256)!=64:
        raise ValueError('Pinned checkpoint required')
    before=capture(chain)
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    collector=ContactEvaluationCollector(admission=chain.admission,output=output/'episodes',
        checkpoint_sha256=checkpoint_sha256,updater=chain.updater)
    results=[]
    try:
        for case in evaluation_cases():
            collector.start(case['name'],case=case,seed=2026092711)
            while collector.active: collector.collect(FrozenPolicy(chain.updater),500)
            raw=json.loads(gzip.decompress((collector.output/case['name']/'episode.json.gz').read_bytes()))
            results.append(dict(case=case,**episode_metrics(raw)))
            _write_json(output/'results.json',results)
            if collector._blocked: raise RuntimeError('Evaluation failed its whole-episode audit')
        if len(collector.replay): raise RuntimeError('Evaluation leaked into replay')
        return results
    except BaseException as exc:
        if collector.active: collector._abort(exc)
        collector.retain_failure(exc)
        _write_json(output/'failure.json',dict(error=repr(exc),attempts=collector.attempts))
        raise
    finally:
        _write_json(output/'attempts.json',collector.attempts)
        if not _same(before,capture(chain)): raise RuntimeError('Evaluation changed training state or RNG')
