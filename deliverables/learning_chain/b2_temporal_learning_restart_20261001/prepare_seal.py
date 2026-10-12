"""Close the one review fix pass only after full clean related protocols."""
import json,os
import validation_contract as C
tests=C.read(C.HERE/'reviewed_restart_green.json')
if tests['tests']!=181 or tests['exit_code'] or tests['failures'] or tests['errors'] or any(tests['actual_calls'].values()):raise ValueError('Final full suite not clean')
for tag,n in [('review_fix_green',3),('fault_evidence_green',1)]:
    r=C.read(C.HERE/(tag+'.json'))
    if r['tests']!=n or r['failures'] or r['errors'] or any(r['actual_calls'].values()):raise ValueError('Review fix not clean')
C.verify_parent()
a=dict(ready=True,critical=0,important=0,minor=0,original_important=2,reviewer='/root/restart_validation_review',
    author_fix_passes=1,rereview_performed=False,tests=181,actual_calls=tests['actual_calls'],effect_verified=False,
    fixes=['real_reader_worker_and_supervisor_chain_red_to_green','started_fault_evidence_and_plot_status_red_to_green'])
with (C.HERE/'review_assessment.json').open('x',encoding='utf-8') as f:json.dump(a,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
with (C.HERE/'progress.md').open('a',encoding='utf-8') as f:
    f.write('\nTask1 complete: new178 RED4 failures→178/178; calls0. Final reviewer Critical0/Important2/Minor0, declined list empty. Final fixed real reader lineage — real Windows RED→GREEN3/3; started-fault retention — RED→GREEN1/1; complete suite181/181 calls0. No new computation or old-file changes. Task2 sealing then authorized launch.\n')
print(json.dumps(a,ensure_ascii=False))
