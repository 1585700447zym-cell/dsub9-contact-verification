"""Final file/cost reconciliation only; no physical or learning computation."""
import ast,json
import paired_contract as C

def main():
    pins=C.read(C.HERE/'execution_pins.json');C.verify(pins['binding_sha256'],pins['authorization_sha256'])
    run=C.HERE/'run';out=C.HERE/'result_analysis';a=C.read(out/'assessment.json')
    l=C.Ledger.load(run/'ledger.json',pins['binding_sha256'],pins['authorization_sha256'])
    assert l.state['status']=='stopped' and l.state['active'] is None and l.state['update_lease'] is None
    assert a['accounting']==l.accounting() and a['costs_complete'] is True and a['reader_audit']['complete'] is True
    assert l.accounting()['new_dynamic_starts']==7 and l.accounting()['formal_batches_completed']==3500
    rows=[r for r in a['rows'] if not r['inherited']]
    assert len(rows)==7 and sum(r['success'] for r in rows)==3 and all(r['simulation_valid'] and r['physical_stopped'] for r in rows)
    assert sum(r['guard_hit'] for r in rows)==1 and all(not a['final_groups'][k] for k in ('F','S'))
    costs=C.read(run/'main_costs.json')
    assert costs['physical_substeps_attempted']==sum(r['physical_substeps'] for r in rows)==394980
    assert costs['optimizer_steps_attempted']==3*3500==10500
    assert costs['model_module_calls_attempted']<=C.scope()['model_module_calls_cap']
    assert C.read(C.HERE/'exit_classification.json')['controlled_stop'] is True
    checkpoints={}
    for folder in run.glob('checkpoint_*'):
        manifest=C.read(folder/'manifest.json');assert C.digest(folder/'state.pt')==manifest['state_sha256']
        assert manifest['binding_sha256']==pins['binding_sha256'] and manifest['authorization_sha256']==pins['authorization_sha256']
        checkpoints[folder.name]=dict(manifest_sha256=C.digest(folder/'manifest.json'),state_sha256=manifest['state_sha256'],batches=manifest['batches'])
    assert len(checkpoints)==9 and checkpoints['checkpoint_F_2000']['batches']==2000 and checkpoints['checkpoint_S_1500']['batches']==1500
    assert C.read(out/'postprocess_execution.json')['calls']==dict(physics=0,model_forward=0,optimizer=0)
    for p in C.HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    for name in ('项目当前入口.md','项目进度跟踪.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md'):
        text=(C.ROOT/name).read_text(encoding='utf-8');current=text.split('<!-- stage-resume-current -->',1)[1].split('<!-- /stage-resume-current -->',1)[0]
        assert '7/18' in current and '3500/5000' in current and '未执行11动态' in current and '1500批余量关闭' in current and '诊断与结论.md' in current
    record=dict(status='passed',execution_source_pins_unchanged=True,parent_seal_unchanged=True,new_dynamic=7,completed_batches=3500,
        all_new_valid_stopped=True,reader_receipts_complete=True,new_costs_complete=True,checkpoints=checkpoints,
        learned_checkpoint_file_integrity=True,learned_checkpoint_independent_physical_restore=False,
        additional_physics_model_optimizer_calls=0,notes='109 checks cover pre-bound execution sources; post-run archive reduction and document clarification checked separately here. No end-to-end method-effectiveness completion claim.')
    C.write(out/'closeout_check.json',record);print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
