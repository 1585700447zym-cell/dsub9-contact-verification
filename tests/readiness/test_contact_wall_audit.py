import importlib


def audit(row):
    spec=importlib.util.find_spec('tools.validation.audit_contact_candidate')
    assert spec is not None,'Strict corresponding pin/hole wall gate is missing'
    return importlib.import_module(spec.name).wall_pairs_pass(row)


def wall():
    return {'passed':True,'contacts':[{'pair':[f'pin_{i:02}',f'hole_convex256_{i:02}_main_000']} for i in range(1,10)]}


def test_wall_requires_all_nine_corresponding_pairs():
    row=wall();assert audit(row)
    row['contacts'].pop();assert not audit(row)


def test_wall_rejects_wrong_hole_even_when_contact_count_is_nonzero():
    row=wall();row['contacts'][0]['pair'][1]='hole_convex256_02_main_000'
    assert not audit(row)


def test_wall_accepts_swapped_pair_order_and_rejects_failed_geometry():
    row=wall();row['contacts'][0]['pair'].reverse();assert audit(row)
    row['passed']=False;assert not audit(row)
