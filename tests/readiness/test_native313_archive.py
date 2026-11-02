import importlib.util
import pytest


def remap():
    spec=importlib.util.find_spec('tools.validation.run_native313_stop')
    assert spec is not None, 'Archive path adapter is missing'
    from tools.validation.run_native313_stop import protocol_inputs
    return protocol_inputs


def test_archive_adapter_corrects_only_known_protocol_reference():
    fix=remap()
    old='deliverables/contact_consistency_repair/候选复验协议.md'
    new='deliverables/native313_validation/候选复验协议.md'
    source={old:'new-digest','controller.py':'unchanged'}
    assert fix(source,'new-digest')=={new:'new-digest','controller.py':'unchanged'}
    assert source=={old:'new-digest','controller.py':'unchanged'}
    assert fix({'other':'digest'},'new-digest')=={'other':'digest'}
    with pytest.raises(ValueError):fix({old:'unexpected'},'new-digest')
    with pytest.raises(ValueError):fix({old:'new-digest',new:'duplicate'},'new-digest')


def test_full_archive_adapter_wiring_without_physics(tmp_path, monkeypatch):
    import json
    import sys
    from pathlib import Path
    import mujoco
    if mujoco.__version__ != '3.13.0':
        pytest.skip('Integration smoke requires isolated 3.13.0')
    from tools.validation import run_native313_stop as entry
    from tools.validation import run_contact_candidate_stop as historical
    original_verify, original_dump, original_out = historical.verify_hashes, historical.dump, historical.OUT
    (tmp_path/'static_extended.json').write_bytes((entry.OUT/'static_extended.json').read_bytes())
    monkeypatch.setattr(entry, 'OUT', tmp_path)
    # This smoke tests archive wiring only; static dependencies have a separate real audit.
    monkeypatch.setattr(entry, 'verify_static_dependencies', lambda: None)
    target=tmp_path/'written.json'
    def simulate_completed_archive():
        expected={entry.OLD_PROTOCOL:entry.sha(entry.ROOT/entry.NEW_PROTOCOL)}
        historical.verify_hashes(entry.ROOT,expected)
        historical.dump(target,{'status':'COMPLETE','protected_inputs':expected})
    monkeypatch.setattr(historical,'main',simulate_completed_archive)
    monkeypatch.setattr(sys,'argv',['adapter','--package-path',str(Path(mujoco.__file__).parents[1]),'--tag','smoke','--timestep','0.0002'])
    entry.main()
    data=json.loads(target.read_text(encoding='utf-8'))
    assert entry.OLD_PROTOCOL not in data['protected_inputs']
    assert entry.NEW_PROTOCOL in data['protected_inputs']
    assert historical.verify_hashes is original_verify
    assert historical.dump is original_dump
    assert historical.OUT == original_out
