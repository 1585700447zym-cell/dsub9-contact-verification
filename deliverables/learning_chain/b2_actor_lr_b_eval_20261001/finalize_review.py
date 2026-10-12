"""Preserve the first seal and append final reviewed rolling-document snapshots."""
import datetime,json,re,shutil
from pathlib import Path
from evaluation_contract import read,digest,verify_files,verify_binding
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
v=read(OUT/'delivery_verification.json')
verify_files(v['results_sha256']);verify_files(v['result_delivery_sha256'])
verify_binding(v['binding_sha256'])
review=OUT/'独立结果审查.md'
review.write_text('''# 独立结果审查（2026-10-01）

只读审阅者：actor_lr_review。未运行模型、物理或训练。

核对 assessment 的11个运行输入摘要、逐项结果、9642周期及actor状态总数；两张图的脚本和渲染未见指标误标或结论越界。

发现并修正一项 Important 文档口径问题：10月月报和交付总览保留了前轮“B未测试”“待确认”的旧当前表述。月报综合摘要、关键数字、负结果与讲稿已统一为A1+B2共3次新增动态、累计60，B已测0/2成功且剩余2点未执行；总览父轮标题及限制明确标为历史，并指向本轮结果。来源日志和历史实验原件保持。

149项相关协议通过，完整冻结B恢复通过；独立实际评价按负X力保护受控停止。该审查不表示策略修复或B.2验收通过。

首次交付摘要和文档快照原样保留；本次仅追加最终文档快照及补充摘要。
''',encoding='utf-8')
docs=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',ROOT/'项目当前入口.md']
snap=OUT/'final_document_snapshot';snap.mkdir(exist_ok=False);links=0
for doc in docs:
    text=doc.read_text(encoding='utf-8')
    for link in re.findall(r'\]\(([^)]+)\)',text):
        if re.match(r'^[a-z]+://',link) or link.startswith('#'):continue
        link=link.split('#')[0].strip('<>')
        if link and not (doc.parent/link).exists():raise ValueError('Missing link: '+link)
        links+=1
    shutil.copyfile(doc,snap/doc.name)
files=[OUT/'delivery_verification.json',review,Path(__file__).resolve(),*snap.iterdir()]
record=dict(status='verified_after_review',time=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
    previous_verification_preserved=True,new_model_or_physics_calls=0,local_links_checked=links,
    review_findings_fixed=['Historical B-not-tested language in current monthly/overview sections'],
    accounting=v['accounting'],b2_complete=False,
    sha256={p.relative_to(ROOT).as_posix():digest(p) for p in files})
with (OUT/'final_review_verification.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({k:x for k,x in record.items() if k!='sha256'},ensure_ascii=False))
