"""Freeze a concrete continuation candidate. File/metadata work only."""
import ast, gzip, json, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent; ROOT = OUT.parents[2]; sys.path.insert(0, str(OUT))
from joint_contract import read, write, sha, digest, LIMITS, learning_config, schedule
from continuation_contract import baseline_rows

if __name__ == '__main__':
    if (OUT / 'delivery_manifest.json').exists(): raise FileExistsError('Never rebuild a sealed candidate')
    previous = OUT.parent / 'b2_warm_import_repair_20261009'
    binding = read(previous / 'source_binding.json')
    inherited = len(binding['files'])
    spec = read(OUT / 'input_spec.json')
    restore = Path(spec['restoration_folder'])
    for name in read(restore / 'delivery_manifest.json')['files']:
        p = restore / name; binding['files'][str(p)] = sha(p)
    binding['files'][str(restore / 'delivery_manifest.json')] = sha(restore / 'delivery_manifest.json')
    config = read(OUT.parent / 'b2_joint_sac_preparation_20261009/configuration.json')
    config['attempts'] = schedule(); write(OUT / 'configuration.json', config)
    codes = ['bootstrap.py', 'joint_contract.py', 'continuation_contract.py', 'execution.py', 'joint_chain.py', 'joint_checkpoint.py',
             'joint_runtime.py', 'joint_rollout.py', 'pilot_worker.py', 'warm_adapter.py', 'run_pilot.py',
             'bounded_io.py', 'phase_deadline.py', 'supervised.py', 'windows_job.py']
    for name in codes + ['configuration.json', 'model.xml', 'input_spec.json']:
        p = OUT / name; ast.parse(p.read_text(encoding='utf8')) if p.suffix == '.py' else None
        binding['files'][str(p)] = sha(p)
    sys.path.insert(1, str(previous))
    from import_graph import collect_graph
    roots=['run_pilot','pilot_worker','warm_adapter','joint_checkpoint','joint_chain','joint_runtime','joint_rollout',
           'tools.validation.run_actor_lr_comparison','tools.validation.run_v4_learning_pilot']
    graph = collect_graph(ROOT, OUT, roots)
    # Source graph is a compatibility inventory; runtime imports remain unexecuted.
    for record in graph['modules'].values():
        if binding['files'].get(record['path'])!=record['sha256']:raise ValueError('Import module outside pinned sources: '+record['path'])
    write(OUT / 'import_audit.json', dict(graph=graph, roots=roots, runtime_import_verified=False, scientific_operations=0,
          limitation='Recognized source imports only; external packages not executed or recursively analyzed'))
    binding['version'] = 'b2_joint_continuation_binding_v1'; binding['parent_binding_sha256'] = sha(previous / 'source_binding.json')
    write(OUT / 'source_binding.json', binding)
    baseline = baseline_rows()
    warm = []
    for source in spec['warmup']:
        raw = json.loads(gzip.decompress(Path(source['archive']).read_bytes()))
        warm.append(dict(id=source['id'], rows=len(raw['transitions']), active_rows=sum(r['action_active'] for r in raw['transitions']),
                         four_dimensional_draws=(len(raw['transitions']) + 49) // 50, archive_sha256=source['archive_sha256']))
    write(OUT / 'inheritance_audit.json', dict(baseline=baseline, warmup=warm, restoration_manifest_sha256=spec['restoration_manifest_sha256'],
          restored_rows=19300, restored_warm_draws=388, new_physical_samples=0, checkpoint_deserialized=False))
    provenance = read(OUT / 'adapter_provenance.json')
    for name in provenance: provenance[name]['final_sha256'] = sha(OUT / name)
    write(OUT / 'adapter_provenance.json', provenance)
    candidate = dict(version='b2_joint_continuation_candidate_v1', stage_id='B2-SCOPE-19', status='PREPARED_NOT_AUTHORIZED',
          training_admitted=False, numeric_continuation_verified=False, cumulative_before=245, cumulative_ceiling=254,
          limits=LIMITS, schedule=schedule(), learning_config_sha256=digest(learning_config()),
          source_binding_sha256=sha(OUT / 'source_binding.json'), input_spec_sha256=digest(spec), import_audit_sha256=sha(OUT / 'import_audit.json'),
          code_sha256={name: sha(OUT / name) for name in codes}, startup_gate='full trainable warm-chain save and independent restore before first environment',
          migration='only state.binding changes to new grant; old four archive bytes and receipts preserved',
          inherited_baseline_sha256=sha(OUT / 'inheritance_audit.json'), physical_model_changed=False,
          accounting_breakdown=dict(parent=dict(learner_constructions=4,tensor_loads=1,checkpoint_saves=2,archive_rebuilds=16),
                                    warm_reader=dict(learner_constructions=2,tensor_loads=1,checkpoint_saves=0,archive_rebuilds=4),
                                    final_reader=dict(learner_constructions=2,tensor_loads=1,checkpoint_saves=0,archive_rebuilds=8)),
          primary_metric=dict(comparison='new F2000 versus inherited matched F0', failure_penalty_s=26, continue_improvement=.10,
                              success_required=4, no_hard_guards=True, independent_test=False), automatic_tracking='PAUSED')
    write(OUT / 'candidate.json', candidate)
    write(OUT / 'authorization_request.json', dict(version='b2_joint_continuation_request_v1', status='NOT_AUTHORIZED', explicit_user_authorized=False,
          candidate_sha256=digest(candidate), binding_sha256=sha(OUT / 'source_binding.json'), cumulative_before=245, limits=LIMITS,
          one_execution=True, retry_allowed=False, carryover_allowed=False, startup_gate=candidate['startup_gate'],
          human_summary='9个新动态回合（在线4＋训练后评价4＋独立恢复物理复现1），最多2000正式更新批；构造8、读取3、保存2、检查点档案重建28（旧预热20＋新在线8）；整体6小时，单物理20分钟、单reader30分钟；先过可训练链保存和独立恢复门，失败立即关闭、不重试。'))
    print(json.dumps(dict(candidate_sha256=digest(candidate), bound_inputs=len(binding['files']), inherited_inputs=inherited), ensure_ascii=False))
