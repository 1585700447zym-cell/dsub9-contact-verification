"""Publish the approved active stage without changing sealed inputs."""
from pathlib import Path
import os
import re
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha


def main():
    if (OUT/'active_document_update.json').exists():raise PermissionError('Active announcement already written')
    reg=read(OUT/'registration.json');counter=read(OUT/'execution/counter.json')
    if counter['status']!='OPEN':raise PermissionError('Run already closed; write final outcome instead')
    after={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==pin,'Concurrent document edit: '+name
        rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        body=('<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-13已批准四点普通SAC有限试跑，正在执行。** '
            '人类已明确批准本次17回合、最多2000批更新、整体6小时的具体新申请，已登记一次性授权。先核验零起点完整保存与独立进程恢复，再执行F0评价4／预热4／在线4／F2000评价4／恢复复现1；失败即停、不重试、不结转。\n\n'
            '当前为运行阶段，结果与实际成本以执行账本为准；正式更新须通过运行内恢复及预热门，不能将授权当作训练成功。累计动态起点237，上限254，独立测试0，完整B.2/C未验收；旧授权关闭，自动跟踪PAUSED（本次在当前会话监督执行）。原3处逐profile覆盖缺口保持。\n\n'
            f'[本次授权]({rel}/grant.json)、[登记]({rel}/registration.json)、[实际进度]({rel}/execution/run/ledger.json)、[已预留操作上界]({rel}/execution/counter.json)。 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->')
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:body,path.read_text(encoding='utf-8'),count=1,flags=re.S);assert n==1
        path.write_text(text,encoding='utf-8');after[name]=sha(path)
    write(OUT/'active_document_update.json',dict(after_documents=after))
    print('Active stage announced in five rolling documents; before snapshots preserved.')


if __name__=='__main__':main()
