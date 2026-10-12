from pathlib import Path
OUT=Path(__file__).resolve().parent;OLD=OUT.parent/'reference_search_20261004'
for name in ['analyze_results.py','audit_results.py']:
    s=(OLD/name).read_text(encoding='utf-8').replace('tmp/matplotlib_reference_search','tmp/matplotlib_deadline25')
    if name=='analyze_results.py':
        s=s.replace("'axis_search_20261004' if name=='y_neg_150'", "'reference_search_20261004' if name=='y_neg_150'")
        s=s.replace("trigger=next((e['time_s'] for e in d['controller_events'] if e['reason']=='LOW_LOAD_SEARCH'),None)", "trigger=20. if name=='y_neg_150' else next((e['time_s'] for e in d['controller_events'] if e['reason']=='LOW_LOAD_SEARCH'),None)")
        s=s.replace("'before first search with new composition'", "('through old 20s deadline' if name=='y_neg_150' else 'before first search; historical other-controller reference only')")
        s=s.replace('deliverables/task_variants/axis_search_20261004/run/y_neg_150.json.gz','deliverables/task_variants/reference_search_20261004/run/y_neg_150.json.gz')
        s=s.replace('Axis-separated search (v6)','Same controller, 20 s task').replace('Drive-reference tracking (v7)','Same controller, 25 s task')
        s=s.replace('Development case -Y 150 um: drive-reference tracking','Development case -Y 150 um: common task deadline 20 vs 25 s')
    (OUT/name).write_text(s,encoding='utf-8')
