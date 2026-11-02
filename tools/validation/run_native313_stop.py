"""Reproduction entry with corrected archive references; no physics changes."""
import argparse
import json
from pathlib import Path
import sys
from tools.validation.run_native313_validation import ROOT, OUT, sha, write, require_static_gate

OLD_PROTOCOL = 'deliverables/contact_consistency_repair/候选复验协议.md'
NEW_PROTOCOL = 'deliverables/native313_validation/候选复验协议.md'


def protocol_inputs(expected, protocol_sha):
    result = dict(expected)
    if OLD_PROTOCOL in result:
        if result[OLD_PROTOCOL] != protocol_sha or NEW_PROTOCOL in result:
            raise ValueError('Unexpected protocol reference; cannot remap')
        result[NEW_PROTOCOL] = result.pop(OLD_PROTOCOL)
    return result


def verify_static_dependencies():
    from tools.validation.validate_training_readiness import verify_hashes
    gate = json.loads((OUT/'static_extended.json').read_text(encoding='utf-8'))
    require_static_gate(gate, '3.13.0')
    verify_hashes(ROOT, gate['source_sha256'])
    for name, keys in [('static_gate_v1/results.json', ('input_sha256','historical_source_sha256')),
                       ('compatibility_comparison.json', ('source_sha256',)),
                       ('compatibility_3.9.0.json', ('source_sha256',)),
                       ('compatibility_3.13.0.json', ('source_sha256','dll_sha256'))]:
        data=json.loads((OUT/name).read_text(encoding='utf-8'))
        for key in keys:verify_hashes(ROOT,data[key])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package-path',type=Path,required=True)
    p.add_argument('--tag',required=True)
    p.add_argument('--timestep',type=float,choices=[.0002,.0001],required=True)
    args=p.parse_args()
    sys.path.insert(0,str(args.package_path.resolve()))
    import mujoco
    if mujoco.__version__!='3.13.0' or not Path(mujoco.__file__).resolve().is_relative_to(args.package_path.resolve()):
        raise ValueError('Explicit isolated 3.13.0 package is required')
    verify_static_dependencies()
    from tools.validation import run_contact_candidate_stop as old
    from tools.validation.validate_training_readiness import new_target
    new_target(OUT,args.tag)
    protocol_sha=sha(ROOT/NEW_PROTOCOL)
    original_verify,original_dump,original_out=old.verify_hashes,old.dump,old.OUT
    protected={Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__)),
               'deliverables/native313_validation/static_extended.json':sha(OUT/'static_extended.json')}
    write(OUT/(args.tag+'_runtime.json'),dict(mujoco_version=mujoco.__version__,module_file=mujoco.__file__,
                                           timestep=args.timestep,source_sha256=protected,archive_adapter=True))
    def verify(root, expected):
        original_verify(root,protocol_inputs(expected,protocol_sha))
    def dump(path, value):
        if 'protected_inputs' in value:
            value={**value,'protected_inputs':protocol_inputs(value['protected_inputs'],protocol_sha)}
        original_dump(path,value)
    old.verify_hashes,old.dump,old.OUT=verify,dump,OUT
    try:
        sys.argv=[sys.argv[0],'--tag',args.tag,'--timestep',str(args.timestep)]
        old.main()
        original_verify(ROOT,protected)
    finally:
        old.verify_hashes,old.dump,old.OUT=original_verify,original_dump,original_out


if __name__=='__main__':main()
