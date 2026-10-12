"""Bind a new finite zero-B2 entry; standard-library preparation only."""
import argparse
import ast
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import baseline_entry  # prohibit scientific imports throughout preparation
import scope_contract as c


def build_binding():
    old=c.read(c.OLD/'source_binding.json')
    files=dict(old['files'])
    for directory in (c.SCOPE,c.PREV):
        seal=c.read(directory/'delivery_manifest.json')
        for rel,pin in seal['files'].items():
            path=directory/rel
            if c.sha(path)!=pin:raise ValueError('Inherited sealed member changed: '+str(path))
            files[str(path)]=pin
        files[str(directory/'delivery_manifest.json')]=c.sha(directory/'delivery_manifest.json')
    files[str(c.OLD/'source_binding.json')]=c.sha(c.OLD/'source_binding.json')
    for name in ('contract.py','baseline_rollout.py','baseline_entry.py'):
        files[str(c.OLD/name)]=c.sha(c.OLD/name)
    for path in sorted(OUT.glob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'));files[str(path)]=c.sha(path)
    for name in ('model.xml','case_registry.json','configuration.json'):
        files[str(OUT/name)]=c.sha(OUT/name)
    config=c.read(OUT/'configuration.json');c.validate_registry(config['cases'])
    return dict(version='b2_stratified_zero_entry_binding_v1',files=files,
        matrix_scope_key=config['common_key'],shared_common_key=config['parent_common_key'],
        executable=old['executable'],runtime_record=old['runtime_record'],
        runtime_record_sha256=old['runtime_record_sha256'],numerical_runtime=old['numerical_runtime'],
        scientific_execution_admitted=False,training_admitted=False,
        inherited_input_count=len(old['files']),prior_actual_delivery_files=77,prior_scope_delivery_files=29)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',required=True,action='store_true');parser.parse_args()
    if (OUT/'execution').exists():raise FileExistsError('Never rebind an attempted package')
    binding=build_binding();c.frozen_module('contract').check_runtime(binding['numerical_runtime'])
    c.write(OUT/'source_binding.json',binding)
    c.verify_binding()
    c.write(OUT/'authorization_request.json',c.grant_template(c.sha(OUT/'source_binding.json'),'pending-new-run-id'))
    c.write(OUT/'qualification_candidate.json',dict(status='ENTRY_PREPARED_OFFLINE_CHECKS_PENDING',
        source_binding_sha256=c.sha(OUT/'source_binding.json'),entry_implemented=True,
        offline_checks_passed=False,fresh_review_completed=False,scientific_execution_admitted=False,
        initial_new21_runtime_qualified=False,nonzero_SAC_qualified=False,training_admitted=False,
        full_B2_accepted=False,C_accepted=False,cumulative_dynamic=258,independent_tests=0,
        automatic_tracking='PAUSED',limits=c.LIMITS))
    print(c.canonical(dict(source_files=len(binding['files']),new_cases=len(c.new_cases()),
        scientific_execution_admitted=False,training_admitted=False)))


if __name__=='__main__':main()
