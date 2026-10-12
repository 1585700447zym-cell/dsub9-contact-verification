"""Read-only historical-byte verification after the actual preflight."""
from execution_contract import HERE,ROOT,read,digest,verify_files,verify_binding,require_authorization
pins=read(HERE/'execution_pins.json');require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
binding=verify_binding(pins['binding_sha256'])
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
sealed=read(old/'sealed_files.json');verify_files(sealed)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
inherited=read(old/'candidate.json')['source_sha256']
for rel,pin in inherited.items():
    if digest(ROOT/mapping.get(rel,rel))!=pin:raise ValueError('Inherited bytes changed: '+rel)
parent=ROOT/'deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis'
for name in ('delivery_verification.json','final_review_verification.json'):
    r=read(parent/name)
    for key in ('sha256','results_sha256','result_delivery_sha256'):
        if key in r:verify_files(r[key])
print({'historical_sealed_files_preserved':len(sealed),'inherited_source_bytes_preserved':len(inherited),
    'current_bound_inputs_preserved':len(binding['input_sha256']),'new_physics_model_optimizer':0})
