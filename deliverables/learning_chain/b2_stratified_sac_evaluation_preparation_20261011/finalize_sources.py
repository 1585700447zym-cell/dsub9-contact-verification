"""Bind implementation and candidate materials; does not grant execution."""
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sac_scope import OUT,ENTRY,read,write,sha,grant_template

def retained_checks(previous,binding_pin):
    same=previous.get('source_binding_sha256')==binding_pin
    return {k:bool(same and previous.get(k) is True) for k in ['offline_checks_passed','fresh_review_completed']}

def bind():
    shutil.copyfile(ENTRY/'model.xml',OUT/'model.xml')
    binding=read(OUT/'source_binding.json')
    for p in list(OUT.glob('*.py'))+[OUT/n for n in ['configuration.json','actors.json','numeric_reference_states.json','evaluation_schedule.json',
        'reuse_catalog.json','model.xml','实施计划.md','seal_format_audit.json']]:binding['files'][str(p)]=sha(p)
    binding.update(runtime_entry_implemented=True,scientific_execution_admitted=False,training_admitted=False)
    write(OUT/'source_binding.json',binding)
    write(OUT/'authorization_requests.json',dict(status='DRAFT_NOT_AUTHORIZED',
        numeric=grant_template('numeric',sha(OUT/'source_binding.json'),'pending-new-run-id'),
        physical=grant_template('physical',sha(OUT/'source_binding.json'),'pending-new-run-id'),
        design_approval_only='按此设计实现离线入口',old_budget_closed=True,automatic_tracking='PAUSED'))
    q=dict(source_binding_sha256=sha(OUT/'source_binding.json'),initial_zero_matrix_verified=True,
        actors_metadata_bound=True,weight_tensor_read=False,numeric_actor_equivalence_passed=False,
        nonzero_dynamic_precheck_passed=False,evaluation_execution_admitted=False,training_admitted=False,
        continuous_scope_qualified=False,runtime_entry_implemented=True,offline_checks_passed=False,
        fresh_review_completed=False,full_B2_accepted=False,C_accepted=False)
    if (OUT/'qualification_candidate.json').exists():
        previous=read(OUT/'qualification_candidate.json')
        q.update(retained_checks(previous,q['source_binding_sha256']))
    write(OUT/'qualification_candidate.json',q)
    print({'source_files':len(binding['files']),'runtime_implemented':True,'numeric_or_physical_admitted':False})

if __name__=='__main__':bind()
