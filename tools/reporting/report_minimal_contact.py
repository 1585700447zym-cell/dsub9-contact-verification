"""Summarize preserved minimal models and independent version probes."""
import argparse
import json
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes

OUT=ROOT/'deliverables/contact_minimal_reproducer'


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);args=p.parse_args();dest=ROOT/args.output_dir
    if dest.exists():raise FileExistsError(dest)
    minimal=json.loads((OUT/'minimal_v2/results.json').read_text(encoding='utf-8'))
    coordinate=json.loads((OUT/'coordinates_v1/results.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,minimal['input_sha256']);verify_hashes(OUT/'minimal_v2',minimal['files'])
    verify_hashes(ROOT,coordinate['input_sha256'])
    before=json.loads((OUT/'version_3p9.json').read_text(encoding='utf-8'))
    after=json.loads((OUT/'version_3p13.json').read_text(encoding='utf-8'))
    rows=[]
    for a,b in zip(before['results'],after['results']):
        assert a['name']==b['name'] and a['geometry']==b['geometry'] and a['qpos']==b['qpos'] and a['xml_sha256']==b['xml_sha256']
        assert sha(OUT/'minimal_v2'/(a['name']+'.xml'))==a['xml_sha256']
        rows.append(dict(name=a['name'],same_compiled_geometry=True,same_pose=True,old_depth_um=a['max_depth_m']*1e6,
                         new_depth_um=b['max_depth_m']*1e6,old_contacts=a['contact_count'],new_contacts=b['contact_count']))
    result=dict(scope='minimal_static_feasibility_not_dynamic_validation',all_three_minimal_reproduced=all(r['reproduced'] for r in minimal['results']),
                version_comparison=rows,production_version='3.9.0',next_candidate='isolated_3.13_native_requires_full_regression',
                training_admitted=False,source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [
                    OUT/'minimal_v2/results.json',OUT/'coordinates_v1/results.json',OUT/'version_3p9.json',OUT/'version_3p13.json',
                    OUT/'reproduce.py',ROOT/'tools/reporting/report_minimal_contact.py']})
    dest.mkdir(parents=True);(dest/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    font();fig,axes=plt.subplots(1,2,figsize=(13,6),layout='constrained')
    axes[0].axis('off')
    axes[0].text(.03,.98,'从完整装配场景缩小到两个碰撞体',va='top',fontsize=16,weight='bold')
    axes[0].text(.03,.86,'完整模型 → 仅保留涉事碰撞 → 两几何体 XML\n\n'
        '三类反例全部逐值重现\n'
        '• 新原生算法异常：223.602 μm\n'
        '• 旧原生算法异常：539.847 μm\n'
        '• 旧 MPR 疑点：3.570487 μm\n\n'
        '编译网格、变换和尺寸保持一致\n'
        '复现不需要控制器或多针接触\n\n'
        '独立包：3 个小型 XML + 一个运行脚本\n'
        '无需原始 CAD、SDF 插件或整份项目',va='top',fontsize=12,linespacing=1.6)
    y=np.arange(3);labels=['新原生反例','旧原生反例','MPR 疑点']
    axes[1].barh(y+.17,[r['old_depth_um'] for r in rows],height=.3,label='3.9.0',color='#aa674b')
    axes[1].barh(y-.17,[r['new_depth_um'] for r in rows],height=.3,label='独立测试 3.13.0',color='#3b8777')
    for i,r in enumerate(rows):
        axes[1].text(r['old_depth_um']+8,i+.17,f"{r['old_depth_um']:.3f}",va='center',fontsize=10)
        label='未返回接触' if r['new_contacts']==0 else f"{r['new_depth_um']:.3g} μm"
        axes[1].text(8,i-.17,label,va='center',fontsize=10)
    axes[1].set_yticks(y,labels);axes[1].set_xlim(0,660);axes[1].invert_yaxis();axes[1].legend(loc='lower right')
    axes[1].set(xlabel='最大接触深度 / μm',title='相同几何与位姿：独立版本对照');axes[1].grid(axis='x',alpha=.2)
    fig.suptitle('D-sub9 可靠性进展：可移植反例与修复路线筛选',fontsize=17)
    fig.supxlabel('结论：新版原生路径值得完整回归；本轮无动力学试验，未升级正式环境，未准入训练。',fontsize=11)
    fig.savefig(dest/'月报_最小复现与版本对照.png',dpi=155);plt.close(fig)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
