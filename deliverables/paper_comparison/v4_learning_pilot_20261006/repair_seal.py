"""Keep the first candidate intact; publish a verified successor seal."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,re,shutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];REL=OUT.relative_to(ROOT).as_posix()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def main():
    old=OUT/'delivery_manifest.json';target=OUT/'delivery_manifest_v2.json'
    if target.exists():raise RuntimeError('Successor already sealed')
    pin=sha(old);assert pin=='d9fa50e53ad91673ace54b32bb6c4e6b8d88db1b90363a8065e394251fab33cb'
    original=json.loads(old.read_text(encoding='utf8'));mismatch=[]
    for name,record in original['files'].items():
        p=OUT/name
        if sha(p)!=record['sha256'] or p.stat().st_size!=record['bytes']:mismatch.append(name)
    assert mismatch==['seal.log'],mismatch
    repair=dict(first_candidate_sha256=pin,first_candidate_retained=True,only_mismatch=mismatch,
        original_log_record=original['files']['seal.log'],final_log_record=dict(sha256=sha(OUT/'seal.log'),bytes=(OUT/'seal.log').stat().st_size),
        verified_other_original_files=len(original['files'])-1,
        cause='封存控制台输出重定向到交付目录内，旧清单读取该日志为空后，退出时stdout才写入。只有控制台日志摘要失配；执行源、原始档案、资格与既有材料未变化。',
        fix='新版本清单绑定稳定最终日志和原清单，并重新核验全目录；原清单/日志/材料原样保留。',
        new_physics=0,new_updates=0)
    write(OUT/'seal_correction.json',repair)
    (OUT/'封存修订说明.md').write_text('''# 封存清单V2

本轮首份清单的控制台日志 seal.log 在签发后才由重定向写入，导致这一项日志摘要不匹配。其余1194个原清单文件逐项摘要一致，执行源、原始回合、学习资格和结果没有变化；没有新计算或训练。

保留原 delivery_manifest.json 和日志，不覆盖历史候选。最终封存以 [delivery_manifest_v2.json](delivery_manifest_v2.json) 为准，V2同时绑定原清单、稳定最终日志、修订说明和滚动文档新快照。[逐项核对与原因](seal_correction.json)。

本轮实际状态不变：2回合，F预热成功/S参考错误，整轮停止，正式更新0、累计142、余26/4000关闭；B.2未完成。
''',encoding='utf8')
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        p=ROOT/name;text=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        note=f'\n\n本轮最终封存以[V2清单]({prefix}{REL}/delivery_manifest_v2.json)为准，[修订原因]({prefix}{REL}/封存修订说明.md)；原候选保留。'
        text=text.replace('<!-- /v4-learning-pilot-current -->',note+'\n<!-- /v4-learning-pilot-current -->',1)
        p.write_text(text,encoding='utf8',newline='\n')
        dest=OUT/'document_snapshot_v2'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
        if p.is_file() and p!=target and '__pycache__' not in p.parts}
    write(target,dict(status='SEALED',version='v4_learning_pilot_manifest_v2',created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        supersedes=pin,original_candidate_retained=True,scope='same finite pilot evidence; final stdout log and rolling document seal corrected',files=files))
    for name,record in files.items():assert sha(OUT/name)==record['sha256'] and (OUT/name).stat().st_size==record['bytes'],name
    print(json.dumps(dict(status='SEALED',version=2,files=len(files),manifest_sha256=sha(target),
        first_candidate_retained=True,original_files_unchanged_except_stdout_log=1194),ensure_ascii=False))
if __name__=='__main__':main()
