"""Correct contact-time wording from existing archives; no simulation imports."""
from pathlib import Path
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
OLD=OUT.parent/'b2_joint_preflight_execution_20261009'
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009'
sys.path.insert(0,str(RUNNER))
from scope_contract import schedule_position

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')

def main():
    if (OUT/'delivery_manifest.json').exists():raise PermissionError('Already sealed')
    before=read(OLD/'document_update.json')['after_documents']
    for name,pin in before.items():
        assert sha(ROOT/name)==pin,'Unexpected current document change: '+name
        dst=OUT/'before_documents'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
    original_manifest=sha(OLD/'delivery_manifest.json')
    previous=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OLD/'verify_delivery.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    preserved=read(OLD/'delivery_manifest.json')['files']
    parent_check=json.loads(previous.stdout.strip().splitlines()[-1])
    episodes=[]
    for name in ('J03_A_AXIS','J04_A_AXIS','J02_B_CORNERS'):
        p=OLD/'run'/(name+'.json.gz');pin=sha(p)
        assert pin==preserved['run/'+p.name]['sha256']
        raw=json.loads(gzip.decompress(p.read_bytes()))
        fast=[(i,c) for i,c in enumerate(raw['cycles']) if schedule_position(raw['spec']['profile'],i)[1]==1]
        peaks=[];end_contacts=0;covered=0
        for i,c in fast:
            end_contact=c['result']['trace_row']['contact_count']
            effect=c['result']['action_log']['effective_command_delta']
            enabled=c['before']['residual_enabled']
            end_contacts+=int(end_contact>0)
            covered+=int(end_contact>0 and enabled and any(abs(v)>1e-15 for v in effect))
            cp=c['result']['cycle_peaks']
            if cp['force_N']>0 or cp['penetration_m']>0:
                peaks.append(dict(cycle_id=i,start_s=c['before']['time_s'],end_s=c['after']['time_s'],
                    endpoint_contact_count=end_contact,residual_enabled=enabled,effective_command_delta=effect,cycle_peaks=cp))
        assert end_contacts==covered==0
        episodes.append(dict(id=name,archive_sha256=pin,fast_cycles=len(fast),endpoint_contact_cycles=end_contacts,
            registered_covered_cycles=covered,internal_peak_cycles=len(peaks),internal_peak_records=peaks))
        del raw,fast
    assert [e['internal_peak_cycles'] for e in episodes]==[3,2,0]
    correction='3处快速块按原登记判据均缺少“周期末有接触且动作有效”的记录；其中J03_A_AXIS有3个、J04_A_AXIS有2个快速周期记录到周期内接触峰值，J02_B_CORNERS未记录到此类峰值。因此不能把这3处统称为“完全没有接触”，也不能据此推断改时序后的结果。'
    evidence=dict(stage_id='B2-SCOPE-10-CORR01',kind='WORDING_AND_EVIDENCE_CLARIFICATION',
        parent_manifest_sha256=original_manifest,episodes=episodes,correction=correction,
        unchanged_route='INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS',physical_attempts=0,new_training=0,
        cumulative_dynamic=237,full_B2_accepted=False,training_admitted=False,automatic_tracking='PAUSED',
        original_coverage_rule_unchanged=True,old_archives_unchanged=True)
    write(OUT/'contact_time_evidence.json',evidence)
    table='\n'.join(f"| {e['id']} | {e['fast_cycles']} | {e['endpoint_contact_cycles']} | {e['internal_peak_cycles']} | {e['registered_covered_cycles']} |" for e in episodes)
    report=f'''# B2-SCOPE-10接触时间口径更正

2026-10-09。当前阶段：B.2；任务：已完成预检的术语澄清与接触记录复核，已完成。本次为资料更正，不计新增研究能力。

此前“3处快速动作块没有遇到接触”的表述过于绝对。原分析只统计了控制周期末的接触记录，把这个结果概括成整个周期没有接触，范围扩大了。

{correction}

| 项目 | 快速块周期数 | 周期末有接触的周期 | 周期内部有接触峰值的周期 | 原登记覆盖周期 |
|---|---:|---:|---:|---:|
{table}

一个控制周期为2毫秒，内部含10个0.2毫秒物理积分子步。因此周期内部出现峰值、周期末接触计数为0可以同时成立。原覆盖条件使用周期末接触、原动作权限及非零有效作用；本次没有事后修改判据。周期内峰值是应保留的接触证据，但不自动替代原登记条件，也不证明持续接触。

“快速”指动作指令每1个控制周期更换，与保持50个周期的测试段比较；不表示提高动作幅度或允许更高速度。

准确的任务名称是“4种位置与姿态联合偏差工况×3类检查，共12次物理仿真”。三类为单轴动作、四轴组合动作、工程触发的停止—回撤—恢复检查。“物理预检”指在动力学接触仿真中预先检查，不是实物连接器实验。“收口”指核对结果、保存完整证据、关闭本轮尝试数量并更新记录，不代表整个B.2验收。

本任务对应[当前计划](../../../研究推进计划_当前版.md)B.2第2项的接触学习工况与代表性动态预检，检查对象也涉及第5项的姿态／联合扰动扩展。联合工况的匹配SAC小规模训练与独立评价仍待；历史其他范围的短训记录保留。

原12/12功能成功、4/4工程恢复通过及3处登记覆盖缺口的结论保留。路线仍为覆盖不足、无追加尝试；累计237，新增物理与训练均0，自动跟踪PAUSED。下一项仍是仅用档案设计覆盖缺口的最小处理方案，并同时区分周期内峰值和周期末接触。旧封存报告不改写，本更正说明与当前项目记录一起使用。

逐周期证据见[contact_time_evidence.json](contact_time_evidence.json)，原始结果见[原报告](../b2_joint_preflight_execution_20261009/结果说明.md)。
'''
    (OUT/'更正说明.md').write_text(report,encoding='utf-8')
    old_sentence='全部时序缺口均为固定快速块与实际接触没有重叠，不能据此推断改时序后的结果。'
    pending={}
    for name in before:
        if name=='AGENTS.md':continue
        p=ROOT/name;t=p.read_text(encoding='utf-8');assert old_sentence in t
        t=t.replace(old_sentence,correction)
        rel=os.path.relpath(OUT/'更正说明.md',p.parent).replace('\\','/')
        note=f'**2026-10-09接触时间口径更正：** 周期末接触为0不等于整个周期无接触。J03/J04各有3/2个快速周期的内部接触峰值；原登记覆盖缺口与路线结论保留。见[更正说明]({rel})。'
        t=t.replace('<!-- /b2-scope-current -->',note+'\n<!-- /b2-scope-current -->',1)
        if name=='项目进度跟踪.md' or name.startswith('deliverables/'):
            t+='\n### 2026-10-09｜B2-SCOPE-10接触时间口径更正\n\n'+correction+' '+note+' 本次只读既有档案，新增物理／训练0，累计237。下一项仍为离线覆盖方案设计，原判据及所有旧封存文件保持。\n'
        pending[name]=t
    for name,t in pending.items():
        assert sha(ROOT/name)==before[name]
        (ROOT/name).write_text(t,encoding='utf-8')
    after={}
    for name in before:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(before_documents=before,after_documents=after,rolling_documents_may_advance=True))
    assert sha(OLD/'delivery_manifest.json')==original_manifest
    for rel,m in preserved.items():assert sha(OLD/rel)==m['sha256']
    for name,t in pending.items():
        assert old_sentence not in t and correction in t and '接触时间口径更正' in t
        assert sha(ROOT/name)==after[name]
    assert not any(m.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for m in sys.modules)
    write(OUT/'verification.json',dict(status='VERIFIED_CONTACT_TIME_CLARIFICATION',parent_verification=parent_check,
        unchanged_parent_manifest=original_manifest,preserved_direct_members=len(preserved),verified_episodes=3,
        documents_updated=5,snapshots=6,new_physical_attempts=0,new_training=0,cumulative_dynamic=237))
    members={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
    write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-10-CORR01',files=members,rolling_documents_may_advance=True))
    for rel,m in read(OUT/'delivery_manifest.json')['files'].items():assert sha(OUT/rel)==m['sha256']
    print(json.dumps(dict(status='VERIFIED',episode_counts=[(e['id'],e['fast_cycles'],e['internal_peak_cycles']) for e in episodes],
        preserved_old_files=1626+len(preserved),sealed_files=len(members),new_physics=0,new_training=0),ensure_ascii=False))

if __name__=='__main__':main()
