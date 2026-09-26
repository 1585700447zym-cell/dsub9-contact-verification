"""Two-case exit-gate experiment, compared against preserved V1 matrix runs."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from tools.control.search_exit_v2 import ExitGateConfig, SearchRecoveryV2
from tools.control.search_recovery import SearchConfig
from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b2 import verified
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.validation.run_b1_baseline import cases, dump
from tools.validation.run_b2_search import hashes, run_search_episode, save_run
from tools.validation.run_contact_cases import ROOT

OUT = ROOT / 'deliverables/b2_exit_gate_v2'
CASE_NAMES = ('x_offset_pos_100um', 'y_offset_neg_100um')
NEW_SOURCES = ('tools/control/search_exit_v2.py', 'tools/validation/run_b2_exit_gate.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    return {**hashes(), **{p: sha(ROOT / p) for p in NEW_SOURCES}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True, choices=CASE_NAMES)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if Path(args.tag).name != args.tag or args.tag in ('.', '..'):
        raise ValueError('Use a new plain folder name')
    target = OUT / args.tag
    if target.exists():
        raise FileExistsError('Preserve earlier attempts; use a new tag')
    old_folder, old_index, old_runs = verified('matrix_v1_7cases')
    assert old_index['source_sha256'] == hashes()
    history = fingerprint()
    assert old_index['historical_source_sha256'] == history
    old_entry = next(e for e in old_index['runs'] if e['case'] == args.case and e['policy'] == 'b2')
    old_run = next(r for r in old_runs if r['case']['name'] == args.case and r['controller']['name'] == 'B2_bounded_search_recovery')
    config = SearchConfig(**old_index['config'])
    gate = ExitGateConfig()
    case = next(c for c in cases() if c.name == args.case)
    code = source_hashes()
    target.mkdir(parents=True)
    (target / 'runs').mkdir()
    for relative in code:
        snapshot = target / 'source_snapshot' / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / relative).read_bytes())
    protocol = {'candidate': 'B2_recovery_exit_v2_first_frozen_trial', 'status': 'RUNNING',
                'config': asdict(config), 'exit_gate': asdict(gate), 'case': asdict(case),
                'source_sha256': code, 'historical_source_sha256': history,
                'reference': {'file': (old_folder / old_entry['file']).resolve().relative_to(ROOT).as_posix(),
                              'sha256': old_entry['sha256'], 'execution': 'preserved_previous_V1_run_not_rerun'},
                'runs': []}
    dump(target / 'results_index.json', protocol)
    env = CartesianEnvironment(segments=256)
    assert env.metadata() == old_run['environment']
    controller = SearchRecoveryV2(config, gate)
    # Saved JSON converts parameter tuples to lists; compare the serialized form.
    assert json.loads(json.dumps(controller.metadata()['admittance'])) == old_run['controller']['admittance']
    run = run_search_episode(env, case, controller)
    for key in ('case', 'environment', 'finish_criteria', 'max_time_s', 'settle_time_s'):
        assert run[key] == old_run[key], key
    run.update(source_sha256=code, historical_source_sha256=history, candidate=protocol['candidate'])
    name = f'runs/{case.name}_b2_v2.json.gz'
    save_run(target / name, run)
    protocol['runs'].append({'file': name, 'sha256': sha(target / name), 'termination': run['termination']})
    dump(target / 'results_index.json', protocol)
    assert code == source_hashes() and history == fingerprint(), 'Inputs changed during experiment'
    assert sha(ROOT / protocol['reference']['file']) == protocol['reference']['sha256']
    protocol['status'] = 'COMPLETE'
    dump(target / 'results_index.json', protocol)
    print(json.dumps({'case': case.name, 'termination': run['termination'],
                      'advance_mm': (run['final']['position_m'][2] - case.start_origin_z_m)*1000,
                      'wall_seconds': run['wall_seconds']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
