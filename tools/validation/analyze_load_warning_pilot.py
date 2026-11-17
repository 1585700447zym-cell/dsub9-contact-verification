"""Pure descriptive evaluation of a closed, fixed-final-weight MLP/GRU pilot.

Reads registration, ledger, receipts and existing audits only. No checkpoint,
simulator, optimizer or raw episode archive is imported or opened. The audits
are evidence inputs, not fresh independent re-audits of the archive bytes.
"""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
from statistics import mean


GROUPS = ('mlp', 'gru')
WARNINGS = ('FORCE_GT5_N', 'FORCE_GT6_N', 'ROTATION_GT2P5_DEG')
DEADLINE = 30.
RECEIPT_KEYS = {
    'episode_id', 'status', 'case', 'seed', 'exploration_seed', 'deterministic',
    'experiment', 'source_checkpoint_sha256', 'archive_sha256', 'outcome',
    'final_reason', 'error', 'valid', 'stopped', 'training_updates', 'task_end_time_s', 'stop_time_s',
}


class _JsonStream:
    """Bounded JSON reader; duplicate native arrays are discarded row by row."""
    def __init__(self, handle):
        self.handle, self.buf, self.offset = handle, '', 0
        self.decoder = json.JSONDecoder()

    def refill(self):
        chunk = self.handle.read(1 << 16)
        self.buf, self.offset = self.buf[self.offset:] + chunk, 0
        return bool(chunk)

    def token(self):
        while True:
            while self.offset < len(self.buf) and self.buf[self.offset].isspace():
                self.offset += 1
            if self.offset < len(self.buf):
                return self.buf[self.offset]
            if not self.refill():
                return ''

    def take(self, expected):
        if self.token() != expected:
            raise ValueError('Invalid JSON delimiter')
        self.offset += 1

    def value(self):
        self.token()
        while True:
            try:
                result, end = self.decoder.raw_decode(self.buf, self.offset)
            except json.JSONDecodeError:
                if self.refill():
                    continue
                raise
            if end < len(self.buf) and self.buf[end] not in ' \t\r\n:,]}':
                if self.refill():
                    continue
                raise ValueError('Invalid JSON value')
            if end == len(self.buf) and self.refill():
                continue
            self.offset = end
            return result

    def members(self, *, object=False):
        first, last = ('{', '}') if object else ('[', ']')
        self.take(first)
        if self.token() != last:
            while True:
                key = self.value() if object else None
                if object:
                    self.take(':')
                yield key
                if self.token() == last:
                    break
                self.take(',')
        self.take(last)

    def discard(self):
        if self.token() == '{':
            for _ in self.members(object=True):
                self.discard()
        elif self.token() == '[':
            for _ in self.members():
                self.value()
        else:
            self.value()


def read_receipt(path):
    result = {}
    with Path(path).open(encoding='utf-8-sig') as handle:
        reader = _JsonStream(handle)
        for key in reader.members(object=True):
            if key in RECEIPT_KEYS:
                result[key] = reader.value()
            else:
                reader.discard()
        if reader.token():
            raise ValueError('Trailing JSON content')
    return result


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid nonnegative finite '+name)
    return float(value)


def _task_load(audit, task_end):
    warning = audit['load_warnings']
    if warning.get('verified') is not True:
        raise ValueError('Native task load is not verified')
    task = warning['exposure']['task']
    duration = _number(task['duration_s'], 'duration_s')
    if duration <= 0 or abs(duration-task_end) > 1e-7:
        raise ValueError('Task exposure boundary differs from task end')
    result = {key:_number(task[key], key) for key in
              ('integral_force_Ns', 'square_integral_force_N2s', 'mean_force_N', 'rms_force_N')}
    if (not math.isclose(result['mean_force_N'], result['integral_force_Ns']/duration, abs_tol=1e-9)
            or not math.isclose(result['rms_force_N']**2, result['square_integral_force_N2s']/duration,
                                abs_tol=1e-9)):
        raise ValueError('Task load moments disagree')
    result['duration_s'] = duration
    result['peak_force_N'] = _number(task['warnings']['FORCE_GT5_N']['peak'], 'task peak force')
    result['peak_rotation_deg'] = math.degrees(_number(
        task['warnings']['ROTATION_GT2P5_DEG']['peak'], 'task peak rotation'))
    result['over_duration_s'] = {}
    result['longest_continuous_s'] = {}
    for name in WARNINGS:
        row = task['warnings'][name]
        over = _number(row['over_duration_s'], name+' duration')
        longest = _number(row['longest_continuous_s'], name+' longest interval')
        if longest > over+1e-9 or over > duration+1e-9:
            raise ValueError('Task warning duration outside task interval')
        result['over_duration_s'][name] = over
        result['longest_continuous_s'][name] = longest
    return result


def normalize_episode(job, receipt, audit, attempt, *, deadline_s=DEADLINE, expected_checkpoint=None):
    """Map one registered job to SUCCESS/FAILURE/INVALID/MISSING, without I/O."""
    row = dict(episode_id=job['episode_id'], policy_mode=job['policy_mode'], pair_id=job['pair_id'],
               status='MISSING', declared_outcome=None, reason=None, issues=[],
               task_time_s=None, decision_time_s=None, penalized_time_s=None, task_load=None,
               source_checkpoint_sha256=None, checkpoint_optimizer_updates=None)
    if receipt is None and audit is None and attempt is None:
        row['reason'] = 'NOT_RUN'
        return row
    issues = row['issues']
    if not isinstance(attempt, dict) or attempt.get('status') != 'AUDITED':
        issues.append('Ledger attempt is not AUDITED')
    elif any(attempt.get(key) != job[key] for key in ('episode_id', 'policy_mode', 'pair_id')):
        issues.append('Ledger job identity differs')
    if not isinstance(receipt, dict) or not isinstance(audit, dict):
        row.update(status='INVALID', reason='INCOMPLETE_EVIDENCE')
        issues.append('Receipt or audit is missing')
        return row
    row.update(declared_outcome=receipt.get('outcome'),
               reason=receipt.get('final_reason') or receipt.get('error'),
               source_checkpoint_sha256=receipt.get('source_checkpoint_sha256'),
               checkpoint_optimizer_updates=audit.get('optimizer_updates'))
    for key in ('episode_id', 'case', 'seed', 'exploration_seed', 'deterministic'):
        if receipt.get(key) != job[key]:
            issues.append('Receipt registration mismatch: '+key)
    for key in ('episode_id', 'policy_mode'):
        if audit.get(key) != job[key]:
            issues.append('Audit registration mismatch: '+key)
    experiment = receipt.get('experiment')
    if not isinstance(experiment, dict) or experiment.get('policy_mode') != job['policy_mode']:
        issues.append('Receipt checkpoint architecture differs')
    if not isinstance(expected_checkpoint, dict):
        issues.append('Ledger final checkpoint binding is missing')
    else:
        final_digest = expected_checkpoint.get('checkpoint_sha256')
        final_updates = expected_checkpoint.get('optimizer_updates')
        if (not isinstance(final_digest, str) or len(final_digest) != 64 or
                any(c not in '0123456789abcdef' for c in final_digest) or
                receipt.get('source_checkpoint_sha256') != final_digest or
                audit.get('source_checkpoint_sha256') != final_digest):
            issues.append('Evaluation source differs from ledger final checkpoint')
        if (type(final_updates) is not int or final_updates < 0 or
                type(audit.get('optimizer_updates')) is not int or
                audit['optimizer_updates'] != final_updates or not isinstance(experiment, dict) or
                type(experiment.get('optimizer_updates')) is not int or
                experiment['optimizer_updates'] != final_updates):
            issues.append('Evaluation optimizer count differs from ledger final checkpoint')
    for key in ('archive_sha256', 'source_checkpoint_sha256'):
        digest = receipt.get(key)
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(c not in '0123456789abcdef' for c in digest) or audit.get(key) != digest):
            issues.append('Receipt/audit binding mismatch: '+key)
    if audit.get('verified') is not True:
        issues.append('Complete audit did not pass')
    if receipt.get('valid') is not True or receipt.get('stopped') is not True:
        issues.append('Simulation or physical stop is not valid')
    if receipt.get('status') != 'finished':
        issues.append('Receipt is not finished')
    if receipt.get('training_updates') != 0:
        issues.append('Evaluation performed optimizer updates')
    if not row['declared_outcome'] or audit.get('task_outcome') != row['declared_outcome']:
        issues.append('Task outcome differs between receipt and audit')
    try:
        duration = _number(receipt.get('task_end_time_s'), 'task_end_time_s')
        row['task_time_s'] = duration
        success = row['declared_outcome'] == 'FULL_SUCCESS'
        decision = _number(audit['stop']['decision_time_s'], 'audit decision_time_s')
        audit_end = _number(audit['stop']['end_time_s'], 'audit end_time_s')
        row['decision_time_s'] = decision
        receipt_decision = _number(receipt.get('stop_time_s'), 'receipt stop_time_s')
        # The 30 s limit constrains active decisions, not the later legal hold.
        # Mirrors the shared load-warning task clock: 1 s settle, 2 s audit tail.
        if (abs(receipt_decision-decision) > 1e-8 or decision > deadline_s+1e-8 or
                not decision-1e-8 <= duration <= decision+1.+1e-8 or
                not duration-1e-8 <= audit_end <= deadline_s+2.+1e-8):
            raise ValueError('Decision/settle/audit clock exceeds registered budget')
        load = _task_load(audit, duration)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        issues.append(str(exc))
    if issues:
        row['status'] = 'INVALID'
    else:
        row.update(status='SUCCESS' if success else 'FAILURE', task_load=load,
                   penalized_time_s=min(duration, deadline_s) if success else deadline_s)
    return row


def _average(values):
    return mean(values) if values else None


def _group_load(rows):
    loads = [row['task_load'] for row in rows]
    if not loads:
        return None
    duration = math.fsum(x['duration_s'] for x in loads)
    integral = math.fsum(x['integral_force_Ns'] for x in loads)
    square = math.fsum(x['square_integral_force_N2s'] for x in loads)
    return dict(episodes=len(loads), sum_task_duration_s=duration,
                max_task_peak_force_N=max(x['peak_force_N'] for x in loads),
                mean_episode_peak_force_N=mean(x['peak_force_N'] for x in loads),
                mean_episode_integral_force_Ns=integral/len(loads), sum_integral_force_Ns=integral,
                time_weighted_mean_force_N=integral/duration,
                time_weighted_rms_force_N=math.sqrt(square/duration),
                over_duration_sum_s={k:math.fsum(x['over_duration_s'][k] for x in loads) for k in WARNINGS},
                longest_continuous_s={k:max(x['longest_continuous_s'][k] for x in loads) for k in WARNINGS})


def summarize_records(records):
    """Describe complete pre-registered pairs; never choose a winning checkpoint."""
    indexed = {}
    for row in records:
        key = row['pair_id'], row['policy_mode']
        if key in indexed:
            raise ValueError('Duplicate evaluation record')
        if row['policy_mode'] not in GROUPS:
            raise ValueError('Unexpected policy mode')
        indexed[key] = row
    pair_ids = sorted({key[0] for key in indexed})
    if not pair_ids or any((p,g) not in indexed for p in pair_ids for g in GROUPS):
        raise ValueError('Complete paired registration required, including missing rows')
    groups = {}
    for group in GROUPS:
        rows = [indexed[p,group] for p in pair_ids]
        count = Counter(row['status'] for row in rows)
        valid = [r for r in rows if r['status'] in ('SUCCESS','FAILURE')]
        success = [r for r in rows if r['status']=='SUCCESS']
        checkpoints = {r['source_checkpoint_sha256'] for r in valid}
        if len(checkpoints) > 1:
            raise ValueError('Frozen checkpoint differs within evaluation group')
        groups[group] = dict(registered_count=len(rows), valid_count=len(valid),
            success_count=count['SUCCESS'], failure_count=count['FAILURE'],
            invalid_count=count['INVALID'], missing_count=count['MISSING'],
            success_rate_registered=len(success)/len(rows),
            success_rate_valid=len(success)/len(valid) if valid else None,
            mean_success_time_s=_average([r['task_time_s'] for r in success]),
            mean_penalized_time_valid_s=_average([r['penalized_time_s'] for r in valid]),
            mean_penalized_time_registered_s=_average([r['penalized_time_s'] for r in valid])
                if len(valid)==len(rows) else None,
            failure_reasons=dict(Counter(r['reason'] for r in rows if r['status']=='FAILURE')),
            invalid_episodes=[r['episode_id'] for r in rows if r['status']=='INVALID'],
            missing_episodes=[r['episode_id'] for r in rows if r['status']=='MISSING'],
            task_load=_group_load(valid))
    pairs = []
    common = []
    for pair in pair_ids:
        left, right = indexed[pair,'mlp'], indexed[pair,'gru']
        valid = all(r['status'] in ('SUCCESS','FAILURE') for r in (left,right))
        success = left['status']==right['status']=='SUCCESS'
        row = dict(pair_id=pair, mlp_status=left['status'], gru_status=right['status'],
                   both_valid=valid, both_success=success,
                   penalized_gru_minus_mlp_time_s=right['penalized_time_s']-left['penalized_time_s'] if valid else None,
                   common_success_gru_minus_mlp_time_s=right['task_time_s']-left['task_time_s'] if success else None,
                   task_load_gru_minus_mlp=None)
        if valid:
            row['task_load_gru_minus_mlp'] = {k:right['task_load'][k]-left['task_load'][k] for k in
                ('peak_force_N','mean_force_N','rms_force_N','integral_force_Ns')}
            row['task_load_gru_minus_mlp']['over_duration_s'] = {
                k:right['task_load']['over_duration_s'][k]-left['task_load']['over_duration_s'][k] for k in WARNINGS}
        if success:
            common.append(pair)
        pairs.append(row)
    return dict(version='load_warning_pilot_evaluation_v1', deadline_s=DEADLINE,
        groups=groups, pairs=pairs, rows=list(records), selection_performed=False,
        common_success=dict(pair_ids=common, count=len(common),
            mean_mlp_time_s=_average([indexed[p,'mlp']['task_time_s'] for p in common]),
            mean_gru_time_s=_average([indexed[p,'gru']['task_time_s'] for p in common]),
            mean_gru_minus_mlp_time_s=_average([
                indexed[p,'gru']['task_time_s']-indexed[p,'mlp']['task_time_s'] for p in common])),
        limitations=['单训练种子、每组两个独立开发工况的小试，不能代表最终测试或泛化成功率。',
            '固定预算结束时的最终权重，不择优权重、不自动排名、不宣布胜者。',
            '共同成功用时有成功子集条件；同时查看完整预登记成功率和失败按30秒计的时间。',
            '30秒限制决策停止时刻；允许其后1秒合法停稳保持。实际成功时间原值报告，时间评分中成功截顶30秒、失败计30秒。',
            '无效及缺失不冒充正常任务失败，也不填充载荷；有效分母必须与预登记分母同时报告。',
            '载荷只取任务段；提前失败具有更短载荷暴露，积分较小不能直接说明控制更优。',
            '依据已有审核与收据的绑定，未重新加载原始大档、运行仿真或更新训练。'])


def _json(path):
    return json.loads(Path(path).read_bytes())


def analyze_batch(batch):
    batch = Path(batch)
    registration, ledger = _json(batch/'registration.json'), _json(batch/'ledger.json')
    if ledger.get('status') not in ('COMPLETED','STOPPED','FAILED','ERROR'):
        raise ValueError('Only a closed batch can be summarized')
    schedule = registration['evaluation_schedule']
    jobs = {j['episode_id']:j for j in schedule}
    if len(jobs) != len(schedule):
        raise ValueError('Duplicate registered episode')
    pair_specs = {}
    for job in schedule:
        if job['deterministic'] is not True or job['split'] != 'dev_eval' or job['policy_mode'] not in GROUPS:
            raise ValueError('Expected deterministic independent development evaluation')
        if Path(job['episode_id']).name != job['episode_id'] or job['episode_id'] in ('.','..'):
            raise ValueError('Invalid registered episode path')
        signature = {k:job[k] for k in ('case','seed','exploration_seed','deterministic','split')}
        prior = pair_specs.setdefault(job['pair_id'], signature)
        if prior != signature:
            raise ValueError('Registered paired cases or seeds differ')
    attempts = {}
    for attempt in ledger['evaluation_attempts']:
        key = attempt['episode_id']
        if key not in jobs or key in attempts:
            raise ValueError('Unregistered or duplicate evaluation attempt')
        attempts[key] = attempt
    rows = []
    for job in schedule:
        folder = batch/'evaluation'/job['episode_id']
        saved, errors = {}, []
        for name, reader in (('receipt', read_receipt), ('audit', _json)):
            path = folder/(name+'.json')
            try:
                saved[name] = reader(path) if path.is_file() else None
            except (OSError, TypeError, ValueError) as exc:
                saved[name] = None
                errors.append(name+' could not be read: '+str(exc))
        row = normalize_episode(job, saved['receipt'], saved['audit'], attempts.get(job['episode_id']),
                                expected_checkpoint=ledger.get('final_checkpoints',{}).get(job['policy_mode']))
        if errors:
            row['status'] = 'INVALID'
            row['issues'].extend(errors)
        rows.append(row)
    result = summarize_records(rows)
    result.update(batch_path=str(batch.resolve()), ledger_status=ledger['status'],
                  final_checkpoints=ledger.get('final_checkpoints',{}),
                  input_files=['registration.json','ledger.json','evaluation/<episode_id>/{receipt,audit}.json'])
    return result


def _fmt(value):
    return '—' if value is None else f'{value:.6f}'


def write_reports(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'pilot_evaluation_summary.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    flat = []
    for row in result['rows']:
        load = row['task_load'] or {}
        item = {k:row[k] for k in ('episode_id','policy_mode','pair_id','status','declared_outcome',
                                   'reason','decision_time_s','task_time_s','penalized_time_s','source_checkpoint_sha256')}
        item['issues'] = '; '.join(row['issues'])
        for key in ('peak_force_N','mean_force_N','rms_force_N','integral_force_Ns','peak_rotation_deg'):
            item['task_'+key] = load.get(key)
        for key in WARNINGS:
            item[key+'_duration_s'] = load.get('over_duration_s',{}).get(key)
        flat.append(item)
    with (output/'pilot_evaluation_rows.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(flat[0]))
        writer.writeheader();writer.writerows(flat)
    lines=['# 配对短训独立开发评估', '',
        '固定各组预算结束时最后权重；本报告只汇总，不择优、不修改训练、不宣布胜者。', '',
        '| 组别 | 预登记/有效 | 成功/失败/无效/缺失 | 成功率（预登记/有效） | 成功平均 s | 有效回合失败罚时平均 s |',
        '|---|---|---|---|---|---|']
    for name,g in result['groups'].items():
        lines.append(f"| {name} | {g['registered_count']}/{g['valid_count']} | "
            f"{g['success_count']}/{g['failure_count']}/{g['invalid_count']}/{g['missing_count']} | "
            f"{_fmt(g['success_rate_registered'])}/{_fmt(g['success_rate_valid'])} | "
            f"{_fmt(g['mean_success_time_s'])} | {_fmt(g['mean_penalized_time_valid_s'])} |")
    lines += ['', '时间评分中失败统一计 30 s，成功用时截顶至 30 s；实际成功/失败时刻另以原值报告。'
              '无效/缺失的评分为空，不混入正常失败。动作预算限制 audit.stop.decision_time_s≤30 s，'
              '允许随后 1 s 内合法停稳保持，因此实际成功时间略过 30 s 不自动算无效。'
              '最终源摘要和优化计数须同时匹配 ledger.final_checkpoints。', '',
              '| 配对工况 | MLP | GRU | 共同成功时间差（GRU−MLP）s | 有效配对罚时差 s |',
              '|---|---|---|---|---|']
    for p in result['pairs']:
        lines.append(f"| {p['pair_id']} | {p['mlp_status']} | {p['gru_status']} | "
            f"{_fmt(p['common_success_gru_minus_mlp_time_s'])} | {_fmt(p['penalized_gru_minus_mlp_time_s'])} |")
    common=result['common_success']
    lines += ['', f"共同成功子集 {common['count']} 对：MLP 平均 {_fmt(common['mean_mlp_time_s'])} s，"
        f"GRU 平均 {_fmt(common['mean_gru_time_s'])} s，配对平均差 {_fmt(common['mean_gru_minus_mlp_time_s'])} s。", '',
        '| 回合 | 状态/原因 | 实际任务 s | 任务峰力 N | 任务平均/RMS N | 任务力积分 Ns | >5N/>6N/>2.5° 时长 s |',
        '|---|---|---|---|---|---|---|']
    for r in result['rows']:
        load=r['task_load'] or {};dur=load.get('over_duration_s',{})
        lines.append(f"| {r['episode_id']} | {r['status']}/{r['reason']} | {_fmt(r['task_time_s'])} | "
            f"{_fmt(load.get('peak_force_N'))} | {_fmt(load.get('mean_force_N'))}/{_fmt(load.get('rms_force_N'))} | "
            f"{_fmt(load.get('integral_force_Ns'))} | "+'/'.join(_fmt(dur.get(k)) for k in WARNINGS)+' |')
    for r in result['rows']:
        if r['issues']:
            lines += ['', f"{r['episode_id']} 无效依据："+'；'.join(r['issues'])+'。']
    lines += ['', *['- '+s for s in result['limitations']], '',
        '逐回合及配对载荷差见同目录 pilot_evaluation_summary.json；平表见 pilot_evaluation_rows.csv。', '']
    (output/'配对短训独立评估.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=analyze_batch(args.batch)
    write_reports(result,args.output or args.batch/'review')
    print(json.dumps(dict(ledger_status=result['ledger_status'],
                          groups={k:{f:g[f] for f in ('registered_count','success_count','failure_count',
                                                     'invalid_count','missing_count')}
                                  for k,g in result['groups'].items()})))


if __name__=='__main__':
    main()
