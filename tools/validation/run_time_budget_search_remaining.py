"""Only the two never-started jobs from batch1, after a stop-audit clock fix."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation import run_time_budget_search_batch as base
from tools.validation.run_yaw_pilot import read,write,sha
from copy import deepcopy
import xml.etree.ElementTree as ET

ORIGINAL=ROOT/'deliverables/learning_chain/time_budget_search_batch1_20261103'
OUT=ORIGINAL/'remaining_M15_S2'
VERSION='time_budget_batch1_never_started_remaining_v1'
CUMULATIVE_BEFORE=453
original_schedule=base.schedule


def schedule():
    return original_schedule()[-2:]


def prepare():
    if OUT.exists():raise FileExistsError('Remaining registration is never replaced')
    old=read(ORIGINAL/'registration.json');summary=read(ORIGINAL/'summary.json')
    if summary['status']!='STOPPED' or summary['initialization_attempts']!=6 or summary['cumulative_initializations']!=453:
        raise ValueError('Exactly six prior attempts required')
    if any((ORIGINAL/'run'/j['id']).exists() for j in schedule()):
        raise ValueError('Only never-started registered jobs may continue')
    if not read(ORIGINAL/'run/S900_P15_S2/supplemental_audit.json')['verified']:
        raise ValueError('Read-only complete supplemental audit required')
    suite=ET.parse(ORIGINAL/'stop_clock_checks.xml').getroot().find('testsuite')
    if int(suite.get('tests'))<30 or int(suite.get('failures')) or int(suite.get('errors')):
        raise ValueError('Stop-clock and remaining pure regressions required')
    changed={p for p,h in old['inputs'].items() if sha(ROOT/p)!=h}
    if changed!={'tools/validation/consistent_sac_audit.py'}:
        raise ValueError('Only the registered stop-audit adapter may differ: '+repr(changed))
    extra=['tools/validation/native_stop_clock.py','tools/validation/run_time_budget_search_remaining.py',
           'tests/test_native_stop_clock.py','tests/test_time_budget_remaining.py',
           'docs/superpowers/plans/2026-11-03-stop-clock-and-remaining.md']
    OUT.mkdir();pins={}
    for rel in sorted(set(old['inputs'])|set(extra)):
        target=OUT/'source_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/rel).read_bytes());pins[rel]=sha(target)
    reg=deepcopy(old)
    reg.update(version=VERSION,inputs=pins,schedule=schedule(),cumulative_before=453,
        max_initializations=2,max_physical_substeps=320000,max_batch_wall_s=2700,
        original_registration_sha256=sha(ORIGINAL/'registration.json'),
        original_summary_sha256=sha(ORIGINAL/'summary.json'),
        supplemental_audit_sha256=sha(ORIGINAL/'run/S900_P15_S2/supplemental_audit.json'),
        stop_clock_checks_sha256=sha(ORIGINAL/'stop_clock_checks.xml'),
        source_changes_from_original=['tools/validation/consistent_sac_audit.py'],
        stop_clock_version='native_event_stop_clock_v1',retry=False,
        authorization='Same user-authorized first batch: only two original never-started jobs; no interrupted/failed job is rerun; total attempts at most eight')
    write(OUT/'registration.json',reg)
    write(OUT/'preparation.json',dict(verified=True,registration_sha256=sha(OUT/'registration.json'),new_initializations=0,new_physical_substeps=0,new_neural_inference=0,new_optimizer_updates=0))
    print('Prepared the two never-started jobs; no retry and no new physics yet')


def ready():
    reg=read(OUT/'registration.json');prep=read(OUT/'preparation.json')
    if (reg['version']!=VERSION or reg['schedule']!=schedule() or reg['cumulative_before']!=453 or
        reg['max_initializations']!=2 or reg['max_physical_substeps']!=320000 or
        reg['total_updates']!=0 or reg['retries']!=0 or reg['retry'] is not False or
        reg['execution_contracts']!={str(v):base.protocol_config(v) for v in (450,900)} or
        prep['registration_sha256']!=sha(OUT/'registration.json')):
        raise ValueError('Remaining schedule/budget changed')
    base.verify_inputs(reg['inputs'])
    for p,key in [(ORIGINAL/'registration.json','original_registration_sha256'),
                  (ORIGINAL/'summary.json','original_summary_sha256'),
                  (ORIGINAL/'run/S900_P15_S2/supplemental_audit.json','supplemental_audit_sha256'),
                  (ORIGINAL/'stop_clock_checks.xml','stop_clock_checks_sha256')]:
        if sha(p)!=reg[key]:raise ValueError('Original evidence changed')
    from tools.validation.run_consistent_sac import select
    select(reg)
    task,referee=base.current_referee()
    if task!=reg['task_id'] or referee!=reg['geometry_referee']:
        raise ValueError('Referee changed')
    return reg


def main():
    # Reuse the reviewed worker/supervisor unchanged; bind all paths and child
    # invocations to this separately frozen continuation registration.
    base.OUT=OUT;base.CUMULATIVE_BEFORE=CUMULATIVE_BEFORE
    base.schedule=schedule;base.prepare=prepare;base.ready=ready
    base.__file__=__file__;base.__doc__=__doc__
    return base.main()


if __name__=='__main__':raise SystemExit(main())
