"""Schedule, live accounting and constraint evidence for the new SAC batch."""
from pathlib import Path
import json
import math
import numpy as np

MAX_CYCLES = 16000
CUMULATIVE_BEFORE = 419


def cases():
    return [dict(name=name, x_offset_m=.0003, y_offset_m=.0003, roll_rad=math.radians(-1.),
        pitch_rad=math.radians(1.), yaw_rad=math.radians(yaw), start_origin_z_m=-.005, target_depth_m=.005)
        for name, yaw in [('YAW_P10',1.), ('YAW_M10',-1.), ('YAW_P15',1.5), ('YAW_M15',-1.5)]]


def schedule():
    result = []
    for stage, repetitions in [('baseline',1), ('warmup',1), ('online',2), ('development',1)]:
        for repeat in range(repetitions):
            for index, case in enumerate(cases()):
                result.append(dict(id=f'{stage}_{repeat+1}_{case["name"]}', stage=stage, case=case,
                    seed=2026092716+index, publish=stage in ('warmup','online'),
                    updates_after=500 if stage == 'online' else 0))
    return result


def _read(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}


def summarize_run(run):
    run = Path(run); entries = []; init = steps = updates = calls = audit_calls = 0
    precise = True; draws = attempts = audit_draws = 0
    for job in schedule():
        folder = run/job['id']
        if not folder.exists(): continue
        receipt, progress = [_read(folder/name) for name in ('receipt.json','progress.json')]
        result, update_progress = [_read(folder/name) for name in ('job_result.json','update_progress.json')]
        attempted = max(receipt.get('reset_attempted',0) or 0, progress.get('reset_attempted',0) or 0)
        physical = max(receipt.get('physical_substeps',0) or 0, progress.get('physical_substeps',0) or 0)
        done_updates = max(result.get('actual_updates_for_job',0) or 0, update_progress.get('actual_updates_for_job',0) or 0)
        neural = max(receipt.get('policy_calls',0) or 0, progress.get('policy_calls',0) or 0)
        complete = result.get('status') == 'FINISHED' and _read(folder/'supervisor.json').get('process_exit_confirmed') is True
        if not complete: precise = False
        init += attempted; steps += physical; updates += done_updates; calls += neural
        audit_calls += result.get('audit_neural_policy_calls',0) or 0
        draws += max(receipt.get('warmup_draws',0) or 0,progress.get('warmup_draws',0) or 0)
        attempts += max(result.get('attempted_updates_for_job',0) or 0,update_progress.get('attempted_updates_for_job',0) or 0)
        audit_draws += result.get('audit_warmup_replays',0) or 0
        entries.append(dict(id=job['id'],stage=job['stage'],case=job['case']['name'],complete=complete,
            cycles=max(receipt.get('control_cycles',0) or 0,progress.get('cycles',0) or 0),
            phase=progress.get('phase'),initializations=attempted,physical_substeps=physical,
            updates=done_updates,policy_calls=neural,outcome=receipt.get('outcome'),reason=receipt.get('final_reason')))
    return dict(episodes=entries,initialization_attempts=init,physical_substeps=steps,training_updates=updates,
        neural_policy_calls=calls,audit_neural_policy_calls=audit_calls,
        warmup_draws=draws,attempted_updates=attempts,audit_warmup_replays=audit_draws,
        completed_episodes=sum(row['complete'] for row in entries),counts_exact=precise,
        cumulative_initializations=CUMULATIVE_BEFORE+init,max_initializations=20,max_training_updates=4000)


def environment_class():
    from .consistent_reference import environment_class as repaired
    Base = repaired()

    class RecordedReferenceEnvironment(Base):
        def _clear_reference_envelope(self):
            super()._clear_reference_envelope()
            self.reference_checks = dict(pre_pd_checks=0,post_step_checks=0,feasible_checks=0,infeasible_checks=0,
                                         max_disk_excess_m=0.,max_lead_excess_m=0.)
            self._reference_hook_index = 0

        def step(self, command):
            self._reference_hook_index = 0
            return super().step(command)

        def _bound_search_reference(self):
            index = self._reference_hook_index; self._reference_hook_index += 1
            active = self.search_reference_center is not None and self.phase == 'RUNNING'
            result = super()._bound_search_reference()
            if active:
                self.reference_checks['pre_pd_checks' if index%2 == 0 else 'post_step_checks'] += 1
                self.reference_checks['feasible_checks' if result else 'infeasible_checks'] += 1
                if result:
                    disk = np.linalg.norm(self.reference[:2]-self.search_reference_center)-self.search_reference_radius
                    lead = np.max(abs(self.reference[:2]-self.data.qpos[:2]))-self.config.reference_lead_m
                    self.reference_checks['max_disk_excess_m'] = max(self.reference_checks['max_disk_excess_m'],float(disk))
                    self.reference_checks['max_lead_excess_m'] = max(self.reference_checks['max_lead_excess_m'],float(lead))
            return result
    return RecordedReferenceEnvironment


def session_class(*, search_xy_limit_m_s=.00045):
    from .consistent_reference import session_class as repaired
    Base = repaired('G1', search_xy_limit_m_s=search_xy_limit_m_s)

    class RecordedReferenceSession(Base):
        def _command_for_action(self, snapshot, action):
            command = super()._command_for_action(snapshot, action)
            center = self.env.search_reference_center
            self.last_action_log.update(reference_before_xy_m=self.env.reference[:2].tolist(),
                actual_before_xy_m=self.env.data.qpos[:2].tolist(),
                reference_center_xy_m=None if center is None else center.tolist())
            return command

        def _trace_row(self, row):
            result = super()._trace_row(row)
            center = self.env.search_reference_center
            result['reference_center_xy_m'] = None if center is None or self.env.phase != 'RUNNING' else center.tolist()
            return result
    return RecordedReferenceSession
