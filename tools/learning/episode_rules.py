"""Versioned episode eligibility. Physical thresholds and historical rules stay fixed."""
import json
import math
from .contact_contract import guard_clear


class StrictRules:
    version = 'guard_clear_v1'
    checkpoint_version = 'bounded_checkpoint_v2'

    def accepts(self, raw):
        return guard_clear(raw)

    def guard_candidate(self, facts):
        return (facts.get('simulation_valid') is True and facts.get('invalid_reasons') == []
                and facts.get('contact_reasons') == [] and facts.get('motion_reasons') == [])

    def receipt_valid(self, receipt):
        return receipt.get('guard_clear') is True

    def stop_reason(self, receipts):
        return None


class ForceOnlyRules(StrictRules):
    version = 'force_only_v1'
    checkpoint_version = 'force_only_checkpoint_v1'

    def guard_candidate(self, facts):
        return (facts.get('simulation_valid') is True and facts.get('invalid_reasons') == []
                and facts.get('motion_reasons') == []
                and facts.get('contact_reasons') in ([], ['FORCE_LIMIT']))

    def classify(self, raw):
        from .audited_replay import AuditedReplay
        from .sac_checkpoint import _audit_physics
        json.dumps(raw, allow_nan=False)  # Includes unsampled facts and stop records.
        facts = raw['guard_facts']; rows = raw['transitions']; case = raw['case']
        force = facts['contact_reasons'] == ['FORCE_LIMIT']
        clear = facts['contact_reasons'] == []
        if (not self.guard_candidate(facts) or raw.get('fault') is not None
                or not 0 < len(rows) <= 13000 or type(facts['checked_substeps']) is not int
                or facts['checked_substeps'] != 10 * len(rows)
                or raw.get('guard_clear') is not clear
                or not 0 <= facts['max_rotation_from_start_rad'] <= math.radians(2.5)):
            raise ValueError('Episode is outside force-only eligibility')
        point = (case['x_offset_m'], case['y_offset_m'])
        train = ((.0001, 0.), (-.0001, 0.), (0., .0001), (0., -.0001))
        holdout = ((.000095, 0.), (-.000095, 0.), (0., .000095), (0., -.000095))
        if (point not in train + holdout or case['roll_rad'] != 0 or case['pitch_rad'] != 0
                or case['start_origin_z_m'] != -.004 or case['target_depth_m'] != .004
                or (point in holdout and raw.get('evaluation_method') not in ('sac', 'zero_b2'))
                or (force and raw.get('evaluation_method') == 'zero_b2')):
            raise ValueError('Unregistered force-only scope or baseline violation')
        if (type(raw['optimizer_steps_start']) is not int or raw['optimizer_steps_start'] < 0
                or raw['optimizer_steps'] != raw['optimizer_steps_start']):
            raise ValueError('In-episode learning is forbidden')
        _audit_physics(raw)  # Recompute outcome and both stopping windows.
        AuditedReplay(capacity=13000)._prepare(rows)  # Full continuity/tensor checks; no publication.
        category = raw['outcome']['task_outcome']
        expected = -10. if force else {'FULL_SUCCESS': 10., 'TASK_FAILURE': -2.}.get(category)
        if expected is None or (force and category != 'CONTACT_GUARD'):
            raise ValueError('Wrong force-only task outcome')
        if not rows[-1]['terminated'] or rows[-1]['truncated'] or rows[-1]['next_action_active']:
            raise ValueError('Complete terminal episode required')
        terminals = []; events = []; previous_time = 0.
        for i, row in enumerate(rows):
            # The frozen environment always advances ten 0.0002 s substeps.
            # Tolerances allow floating-point clock accumulation, not a new rate.
            end_time = row['trace_row']['time_s']
            if (not math.isclose(row['dt'], .0002*10, rel_tol=0, abs_tol=1e-12)
                    or not math.isclose(end_time, (i+1)*.002, rel_tol=0, abs_tol=1e-9)
                    or not math.isclose(end_time-previous_time, row['dt'], rel_tol=0, abs_tol=1e-12)):
                raise ValueError('Transition differs from frozen physical clock')
            for event in row['events']:
                t = event['time_s']
                if (not previous_time-1e-9 <= t <= end_time+1e-9
                        or (events and t < events[-1]['time_s'])):
                    raise ValueError('Event is outside its recorded control cycle')
                events.append(event)
            previous_time = end_time
            terms = row['reward_terms']; log = row['action_log']
            if terms['terminal'] != 0: terminals.append((i, terms['terminal']))
            if (not math.isclose(row['reward'], terms['total'], rel_tol=0, abs_tol=1e-12)
                    or not math.isclose(terms['total'], sum(terms[k] for k in ('progress', 'time', 'force', 'torque', 'terminal')), rel_tol=0, abs_tol=1e-12)
                    or terms['force'] > 0 or terms['torque'] > 0):
                raise ValueError('Reward arithmetic differs')
            action = log['raw_action']
            if len(action) != 4 or any(not -1 <= x <= 1 for x in action):
                raise ValueError('Invalid normalized request')
            requested = [action[0]*.00015, action[1]*.00015, 0., action[2]*.0005, action[3]*.0005, 0.]
            if (len(log['requested_residual']) != 6
                    or any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-18) for a, b in zip(requested, log['requested_residual']))
                    or type(log['enabled']) is not bool or log['enabled'] != row['action_active']
                    or log['applied_residual'] != (requested if log['enabled'] else [0.]*6)
                    or row['action'] != (action if log['enabled'] else [0.]*4)):
                raise ValueError('Action request/command/replay mapping differs')
        if terminals != [(len(rows)-1, expected)]:
            raise ValueError('Unique terminal reward differs')
        if (not math.isclose(raw['audit_end_time_s'], previous_time, rel_tol=0, abs_tol=1e-9)
                or not math.isclose(math.fsum(r['dt'] for r in rows), previous_time, rel_tol=0, abs_tol=1e-9)):
            raise ValueError('Episode duration and audit clock differ')
        if events != raw['events']:
            raise ValueError('Per-cycle and complete event streams differ')
        guard_names = {'FORCE_LIMIT', 'TORQUE_LIMIT', 'PENETRATION_LIMIT', 'ROTATION_LIMIT',
                       'SPEED_LIMIT', 'ANGULAR_SPEED_LIMIT', 'TRAVEL_LIMIT'}
        found = {r for e in raw['events'] for r in e['reason'].split('+') if r in guard_names}
        if found != set(facts['contact_reasons']):
            raise ValueError('Guard events and latched facts differ')
        if force:
            hits = [i for i, r in enumerate(rows) if any('FORCE_LIMIT' in e['reason'].split('+') for e in r['events'])]
            if not hits or rows[hits[0]]['next_action_active'] or any(r['action_active'] or r['action'] != [0.]*4 for r in rows[hits[0]+1:]):
                raise ValueError('Force guard did not disable subsequent actions')
            row = rows[hits[0]]
            if .025*math.sqrt(-row['reward_terms']['force']/(.2*row['dt'])) <= .025:
                raise ValueError('Force event lacks a corresponding cycle peak')
        return dict(version=self.version, kind='force_failure' if force else 'guard_clear')

    def accepts(self, raw):
        try:
            self.classify(raw)
            return True
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            return False

    def receipt_valid(self, receipt):
        stamp = receipt.get('learning_eligibility')
        force = receipt.get('task_outcome') == 'CONTACT_GUARD'
        return (receipt.get('guard_clear') is (not force)
                and receipt.get('task_outcome') in ('FULL_SUCCESS', 'TASK_FAILURE', 'CONTACT_GUARD')
                and stamp == dict(version=self.version, kind='force_failure' if force else 'guard_clear'))

    def stop_reason(self, receipts):
        total = consecutive = 0
        for receipt in receipts:
            force = receipt['task_outcome'] == 'CONTACT_GUARD'
            total += force
            consecutive = consecutive + 1 if force else 0
            if consecutive >= 2: return 'two_consecutive_force_failures'
            if total >= 3: return 'three_total_force_failures'
        return None


STRICT = StrictRules()
FORCE_ONLY = ForceOnlyRules()


def rules_for(admission):
    rules = getattr(type(admission), 'episode_rules', STRICT)
    if rules is not STRICT and rules is not FORCE_ONLY:
        raise ValueError('Unknown episode eligibility rules')
    return rules


def stamp_pending(raw, record, rules):
    """Only new rules add metadata; the old strict archive format stays intact."""
    raw['guard_clear'] = guard_clear(raw)
    record['guard_clear'] = raw['guard_clear']
    if rules is STRICT:
        accepted = rules.accepts(raw) and 0 < len(raw['transitions']) <= 13000
        raw['guard_clear'] = record['guard_clear'] = accepted
    else:
        try:
            stamp = rules.classify(raw)
            accepted = True
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            stamp = dict(version=rules.version, kind='rejected')
            accepted = False
        raw['learning_eligibility'] = record['learning_eligibility'] = stamp
    if not accepted:
        raw['outcome']['valid_for_learning'] = False
    return accepted
