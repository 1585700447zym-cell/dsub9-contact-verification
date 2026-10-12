"""Fresh 20k target run, with no target-induced episode truncation."""
from pathlib import Path
import time

from .admitted_collection import _write_json
from .sac_checkpoint import save_checkpoint
from .sac_collection import qualified_update_limit


def run_training(chain, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    if chain.budget.total or chain.history or chain.collector.attempts:
        raise ValueError('First engineering short training must start fresh')
    limit = qualified_update_limit(chain.admission)
    if limit != 8250: raise ValueError('Formal training admission required')
    receipts = []; timings = []; started = time.perf_counter()
    try:
        while chain.budget.total < 20000:
            identity = f'train_{len(chain.collector.attempts):06d}'
            begin = time.perf_counter(); chain.start(identity)
            reset_wall = time.perf_counter() - begin
            audit_before = getattr(chain.collector, 'audit_archive_wall_s', 0.)
            begin = time.perf_counter()
            while chain.collector.active:
                result = chain.collect(500)
                print(f'{identity}: {result}', flush=True)
            collect_wall = time.perf_counter() - begin
            audit_wall = getattr(chain.collector, 'audit_archive_wall_s', 0.) - audit_before
            if chain.budget.total > 33000: raise RuntimeError('Whole-episode training bound exceeded')
            begin = time.perf_counter()
            if chain.budget.available: chain.update(chain.budget.available)
            if chain.budget.available: raise RuntimeError('Earned update credit was not exhausted')
            update_wall = time.perf_counter() - begin
            _write_json(output / 'attempts.json', chain.collector.attempts)
            _write_json(output / 'updates.json', chain.history)
            path = output / 'checkpoints' / identity
            begin = time.perf_counter(); sha = save_checkpoint(chain, path)
            checkpoint_wall = time.perf_counter() - begin
            receipts.append(dict(episode_id=identity, path=path.relative_to(output).as_posix(), sha256=sha,
                cumulative_audited=chain.budget.total, critic_updates=chain.updater.counts['critic'],
                bytes=(path / 'state.pt').stat().st_size))
            timings.append(dict(episode_id=identity, reset_wall_s=reset_wall,
                collection_wall_s=collect_wall - audit_wall, audit_archive_wall_s=audit_wall,
                update_wall_s=update_wall, checkpoint_wall_s=checkpoint_wall))
            _write_json(output / 'checkpoint_receipts.json', receipts)
            _write_json(output / 'timings.json', timings)
            print(f'{identity}: audited={chain.budget.total}, updates={chain.updater.counts}, checkpoint={sha}', flush=True)
        report = dict(training_completed=True, target_audited_cycles=20000, cumulative_audited=chain.budget.total,
            overshoot_cycles=chain.budget.total - 20000, attempts=len(chain.collector.attempts),
            update_counts=chain.updater.counts, credit_remaining=chain.budget.available,
            final_checkpoint=receipts[-1], training_wall_s=time.perf_counter() - started, timings=timings)
        _write_json(output / 'training.json', report)
        return report
    finally:
        _write_json(output / 'attempts.json', chain.collector.attempts)
        _write_json(output / 'updates.json', chain.history)
