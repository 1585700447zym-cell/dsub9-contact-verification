def test_case_discovery_excludes_source_snapshot_directory():
    from tools.validation.verify_guard_baseline import development_cases
    names = development_cases()
    assert len(names) == 7
    assert 'source_snapshot' not in names
    assert 'aligned' in names and 'combined_a' in names


def test_candidate_aligned_reintegrates_exact_history_without_new_faults(runtime):
    from tools.validation.verify_guard_baseline import run_case
    result = run_case('aligned')
    assert result['exact_history_match'] is True
    assert result['outcome']['task_outcome'] == 'FULL_SUCCESS'
    assert result['outcome']['physical_stopped'] is True
    assert result['guard_facts']['motion_reasons'] == []
    assert result['guard_facts']['contact_reasons'] == []
    assert result['training_admitted'] is False


def test_invalid_native_time_is_archivable_not_lost(runtime, monkeypatch):
    import json
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.validation.verify_guard_baseline import run_case
    advance = CandidateEpisodeSession.advance_cycle
    def invalid_time(self, action):
        self.env.data.time = float('nan')
        return advance(self, action)
    monkeypatch.setattr(CandidateEpisodeSession, 'advance_cycle', invalid_time)
    report = run_case('aligned')
    assert report['exact_history_match'] is False
    assert report['outcome']['simulation_valid'] is False
    encoded = json.dumps(report, allow_nan=False)
    assert 'nonfinite' in encoded


def test_candidate_fingerprint_covers_model_controller_config_and_audit():
    from tools.validation.guard_evidence import input_fingerprints
    hashes = input_fingerprints()
    required = ['tools/dynamics/cartesian.py', 'tools/control/search_recovery.py',
                'tools/validation/native313_matrix_audit.py',
                'tools/validation/run_contact_candidate_stop.py',
                'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json',
                'models/dsub9_pair.xml', 'models/includes/dsub9_collision.xml']
    assert all(name in hashes for name in required)
    assert any(name.startswith('assets/') for name in hashes)
    assert all(len(hashes[name]) == 64 for name in required)
