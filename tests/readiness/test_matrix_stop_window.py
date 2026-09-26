import importlib.util
import math


def helpers():
    spec=importlib.util.find_spec('tools.validation.native313_matrix_audit')
    assert spec is not None, 'Actual stop clock and invalid-value archive helpers missing'
    from tools.validation import native313_matrix_audit
    return native313_matrix_audit


def test_recovery_timeout_does_not_restart_two_second_stop_budget():
    h=helpers()
    events=[dict(time_s=1.,phase='STOPPING',reason='B2_SEARCH_EXHAUSTED')]
    assert h.actual_stop_start(events,2.)==1.
    rows=[dict(time_s=i*.0002,linear_m_s=0 if i*.0002>=3.1 else 2e-5,angular_rad_s=0.) for i in range(5001,20001)]
    assert not h.actual_stop_pass(rows,events,2.,4.,.0002)
    for r in rows:r['linear_m_s']=0.
    assert h.actual_stop_pass(rows,events,2.,4.,.0002)


def test_nonfinite_fault_samples_are_preserved_without_becoming_valid_data():
    import json
    h=helpers()
    original={'sample':[float('nan'),float('inf'),-float('inf'),1.]}
    clean=h.archive_nonfinite(original)
    json.dumps(clean,allow_nan=False)
    assert clean['sample']==[{'nonfinite':'nan'},{'nonfinite':'inf'},{'nonfinite':'-inf'},1.]
    assert math.isnan(original['sample'][0])
    assert not h.samples_finite([dict(time_s=1.,linear_m_s=clean['sample'][0],angular_rad_s=0.)])


def test_latched_guard_note_does_not_restart_stop_clock_but_retract_does():
    h=helpers()
    events=[dict(time_s=1.,phase='STOPPING',reason='B2_SEARCH_EXHAUSTED'),
            dict(time_s=1.8,phase='STOPPING',reason='B2_LATCHED_FORCE_LIMIT')]
    assert h.actual_stop_start(events,2.)==1.
    events += [dict(time_s=2.,phase='RETRACT',reason='RECOVERY_ACCEPTED'),
               dict(time_s=3.,phase='STOPPING',reason='RECOVERY_COMPLETE')]
    assert h.actual_stop_start(events,3.)==3.
