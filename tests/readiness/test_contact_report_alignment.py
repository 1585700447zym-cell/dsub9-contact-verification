import tools.reporting.report_contact_candidate as report


def rows(times):return [{'time_s':t} for t in times]


def test_partial_physics_step_does_not_break_common_time_alignment():
    assert hasattr(report,'common_rows'),'Failure report must align real common timestamps'
    a,b=report.common_rows(rows([0.,.002,.004,.006]),rows([0.,.002,.0036]))
    assert [r['time_s'] for r in a]==[0.,.002]
    assert [r['time_s'] for r in b]==[0.,.002]


def test_common_time_alignment_allows_roundoff_but_never_extrapolates():
    assert hasattr(report,'common_rows'),'Failure report must align real common timestamps'
    a,b=report.common_rows(rows([0.,.002,.004]),rows([0.,.002+1e-12,.0044]))
    assert len(a)==len(b)==2
