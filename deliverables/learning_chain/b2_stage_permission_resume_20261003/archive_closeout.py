"""Supplementary read-only archive reduction after the bounded run stopped.

No simulator/network/optimizer import or invocation. Execution sources remain sealed.
"""
import gzip,json,math,statistics,os
import paired_contract as C

def main():
    pins=C.read(C.HERE/'execution_pins.json');C.verify(pins['binding_sha256'],pins['authorization_sha256'])
    out=C.HERE/'result_analysis';a=C.read(out/'assessment.json')
    assert a['status']=='stopped' and a['costs_complete'] and a['accounting']['formal_batches_completed']==3500
    rows=[r for r in a['rows'] if not r['inherited']]
    assert len(rows)==7 and sum(r['guard_hit'] for r in rows)==1
    failure=next(r for r in rows if r['guard_hit']);path=C.ROOT/failure['archive_path']
    assert C.digest(path)==failure['archive_sha256']
    raw=json.loads(gzip.decompress(path.read_bytes()));trans=raw['transitions']
    resume=next(e['time_s'] for e in raw['events'] if e['reason']=='B2_RECOVERY_RESUMED')
    resumed=[r for r in trans if r['trace_row']['time_s']>=resume and r['action_active']]
    summary=dict(archive_sha256=failure['archive_sha256'],events=raw['events'],outcome=raw['outcome'],guard_facts=raw['guard_facts'],
        final_xy_um=failure['final_xy_error_m']*1e6,force_peak_N=failure['force_peak_N'],
        resumed_active_cycles=len(resumed),resumed_policy_phases=sorted({r['trace_row']['policy_phase'] for r in resumed}),
        raw_action_axes=['x','y','roll','pitch'],
        resumed_raw_action_mean=[statistics.mean(r['action_log']['raw_action'][i] for r in resumed) for i in range(4)],
        resumed_raw_action_abs_ge_095_fraction=[sum(abs(r['action_log']['raw_action'][i])>=.95 for r in resumed)/len(resumed) for i in range(4)],
        calls=dict(physics=0,model_forward=0,optimizer=0),scope='read stored transitions only; no counterfactual rollout or new critic score')
    C.write(out/'failure_archive_summary.json',summary)
    precision=[]
    for result in a['rows']:
        if result['case_index']!=2 or result['stage'] not in ('b2','warmup','online'):continue
        source=C.ROOT/result['archive_path'];assert C.digest(source)==result['archive_sha256']
        episode=json.loads(gzip.decompress(source.read_bytes()));phases={}
        for phase in ('INSERT','SEARCH'):
            active=[r for r in episode['transitions'] if r['action_active'] and r['trace_row']['policy_phase']==phase]
            phases[phase]=dict(active_cycles=len(active),raw_action_mean=[statistics.mean(r['action_log']['raw_action'][i] for r in active) for i in range(4)] if active else None)
        precision.append(dict(id=result['id'],source_sha256=result['archive_sha256'],success=result['success'],xy_um=result['final_xy_error_m']*1e6,
            training_batches=result['training_batches'],episode_return=result['return'],phases=phases,events=episode['events']))
    C.write(out/'precision_archive_comparison.json',dict(rows=precision,calls=dict(physics=0,model_forward=0,optimizer=0),note='Descriptive stored-action comparison, not controlled single-axis causal evidence'))
    os.environ['MPLCONFIGDIR']=str(C.ROOT/'tmp/learning_mpl_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
    for key,offset,color in [('B2',-.25,'#8b929a'),('F',0.,'#286c99'),('S',.25,'#27856c')]:
        source=a['final_groups']['B2'] if key=='B2' else [r for r in rows if r['arm']==key]
        by_case={r['case_index']:r for r in source};values=[by_case[i]['final_xy_error_m']*1e6 if i in by_case else np.nan for i in range(4)]
        ax.bar(np.arange(4)+offset,values,width=.23,color=color,label='继承B2' if key=='B2' else key+'在线采集')
        for i,value in enumerate(values):
            if math.isnan(value):ax.text(i+offset,5,'未执行',rotation=90,ha='center',va='bottom',fontsize=9,color=color)
            else:ax.text(i+offset,value+2,f'{value:.1f}'+('\n力保护' if by_case[i]['guard_hit'] else ''),ha='center',va='bottom',fontsize=9,color=color)
    ax.axhline(50,color='#b03532',linestyle='--',label='XY成功必要条件50 μm')
    ax.set_xticks(range(4),['+X / 500批','−X / 1000批','+Y / 1500批','−Y / 2000批'])
    ax.set_ylim(0,185);ax.set_ylabel('停稳后的XY误差 / μm');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    ax.legend(loc='upper left',ncol=2,fontsize=9)
    ax.set_title('已完成的在线回合：各方向学习进度不同，不能作为冻结策略成功率\nF2000负Y触发停止；S负Y及全部2500批冻结评价未执行',fontsize=11)
    fig.savefig(out/'online_results.png',dpi=160);fig.savefig(out/'online_results.pdf');plt.close(fig)
    # Clarify unfinished cells in the current, not-yet-sealed generated report.
    p=out/'结果说明.md';text=p.read_text(encoding='utf-8')
    original=out/'结果说明_原始生成.md'
    if not original.exists():original.write_text(text,encoding='utf-8')
    text=text.replace('| F | 0/4 | 0/0 |','| F | 0/4 | 未执行 |').replace('| S | 0/4 | 0/0 |','| S | 0/4 | 未执行 |')
    addition='\n\n## 本轮停止原因与下一步\n\n见[归档诊断与结论](诊断与结论.md)。下图只展示已完成在线回合，不是相同最终检查点的性能比较。\n\n![在线回合诊断](online_results.png)\n'
    if '## 本轮停止原因与下一步' not in text:text+=addition
    p.write_text(text,encoding='utf-8')
    print(json.dumps(dict(failure=summary,positive_y_comparison=precision),ensure_ascii=False))

if __name__=='__main__':main()
