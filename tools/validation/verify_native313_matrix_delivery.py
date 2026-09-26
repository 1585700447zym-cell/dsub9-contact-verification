"""Read-only evidence and actual-stop-window audit of the frozen paired matrix."""
import json
from tools.validation.run_native313_matrix import ROOT,OUT,classify_episode
from tools.validation.validate_training_readiness import verify_hashes,sha
from tools.validation.native313_matrix_audit import actual_stop_pass,actual_stop_start,samples_finite
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.measure_readiness_stop import stop_qualified
from tools.validation.run_b1_baseline import geometric_finish
from tools.validation.run_b2_search import read_run


def main():
    manifest=json.loads((OUT/'delivery_manifest.json').read_text(encoding='utf-8'));verify_hashes(ROOT,manifest)
    assessment=json.loads((OUT/'report_v1/assessment.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,assessment['source_sha256']);checked=0
    for policy in ('b1','b2'):
        base=OUT/(policy+'_v1');index=json.loads((base/'results_index.json').read_text(encoding='utf-8'))
        assert index['status']=='COMPLETE' and len(index['runs'])==7
        verify_hashes(ROOT,index['protected_inputs']);verify_hashes(ROOT,index['historical_source_sha256'])
        for entry in index['runs']:
            p=base/entry['file'];assert sha(p)==entry['sha256']
            audit=json.loads(p.read_text(encoding='utf-8'));verify_hashes(p.parent,audit['files'])
            raw=read_run(p.parent/'original.json.gz');tail=read_run(p.parent/'stop_extension.json.gz')
            assert raw['final']==tail['trace'][0] and audit['final']==tail['trace'][-1]
            final=tail['trace'][-1];end=final['time_s'];start=actual_stop_start(tail['events'],raw['stop_time_s'])
            hold=samples_finite(tail['physical_stop_samples']) and physical_tail_pass(tail['physical_stop_samples'],end,.0002)
            budget=actual_stop_pass(tail['physical_stop_samples'],tail['events'],raw['stop_time_s'],end,.0002)
            stopped=bool(budget and hold and final['phase']=='STOPPING')
            safe=bool(start is not None and stop_qualified(phase=final['phase'],events=tail['events'],recorded_time_s=end,
                      deadline_s=start+2.,confirmed=budget,final_stable=hold,peaks=tail['peaks']))
            classification=classify_episode(termination=raw['termination'],phase=final['phase'],events=tail['events'],
                              finite=audit['finite'],stopped=stopped,safe=safe,final_geometry=geometric_finish(final))
            row=next(r for r in assessment['rows'] if r['case']==entry['case'] and r['policy']==policy)
            assert all(row[k]==v for k,v in classification.items())
            assert row['physical_stopped']==stopped and row['actual_two_second_budget_pass']==budget
            checked+=1
    ready=all(r['candidate_data_valid'] for r in assessment['rows'])
    assert len(assessment['rows'])==checked==14 and ready==assessment['interface_implementation_admitted']
    print(f"PASS: {len(manifest)} delivery files, 14 raw archives and actual-stop verdicts; {assessment['status']}; SAC not started")


if __name__=='__main__':main()
