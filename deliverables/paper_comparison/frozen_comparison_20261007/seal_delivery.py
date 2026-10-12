"""Seal stage once; no stdout redirection into this tree while hashing."""
from pathlib import Path
import json,hashlib,datetime,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    manifest=OUT/'delivery_manifest.json';assert not manifest.exists()
    assert read(OUT/'closure_verification.json')['passed'] and read(OUT/'figure_qa.json')['passed']
    cfg=read(OUT/'configuration.json');prior=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
    assert all(sha(ROOT/n)==d for n,d in read(prior/'configuration.json')['input_sha256'].items())
    assert all(sha(ROOT/n)==d for n,d in cfg['evaluation_input_sha256'].items())
    paths=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    links=0
    for n in paths:
        p=ROOT/n;assert sha(p)==sha(OUT/'documents_snapshot'/n)
        s=re.search(r'<!-- pc07-current -->.*?<!-- /pc07-current -->',p.read_text(encoding='utf8'),re.S).group()
        assert 'PC-07收口' in s
        for target in re.findall(r'\]\(([^)]+)\)',s):
            d=(p.parent/target).resolve();assert d.exists() or d==manifest,target;links+=1
    for target in re.findall(r'\]\(([^)]+)\)',(OUT/'结果说明.md').read_text(encoding='utf8')):
        d=(OUT/target).resolve();assert d.exists() or d==manifest,target;links+=1
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
        if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    m=dict(status='SEALED',created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        scope='single-seed frozen matched comparison, initial-policy controls and prospectively registered first-use positions; no blanket B2/C/paper superiority claim',
        rolling_documents='immutable snapshots; originals may advance',files=files,local_links_checked=links)
    manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    assert all(sha(OUT/n)==v['sha256'] and (OUT/n).stat().st_size==v['bytes'] for n,v in files.items())
    print(json.dumps(dict(status='SEALED',files=len(files),sha256=sha(manifest),local_links_checked=links)))
if __name__=='__main__':main()
