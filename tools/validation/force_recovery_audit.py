"""Read-only native recovery proof; never erase historical protection facts."""
import math


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Finite recovery evidence required')
    return value


def _close(a, b):
    return abs(_number(a) - _number(b)) <= 1e-9


def verify_recovery_evidence(record, *, cycle_peaks, facts, end_time_s,
                             timestep=.0002, control_period=.002,
                             wait_stable_s=1., recovery_time_limit_s=1.):
    """Recompute eligibility from native samples, rather than trusting status."""
    events, samples = record['events'], record['samples']
    if not isinstance(events, list) or not isinstance(samples, list):
        raise ValueError('Recovery event/sample lists required')
    peak = max((_number(p['force_N']) for p in cycle_peaks), default=0.)
    if (not _close(peak, record['peak_force_N']) or
            ('FORCE_LIMIT' in facts['contact_reasons']) != (peak > 5.)):
        raise ValueError('Historical force facts and native cycle peaks disagree')
    completed = sum(e['status'] == 'COMPLETED' for e in events)
    if (record['force_recovery_count'] != len(events) or
            record['completed_force_recovery_count'] != completed or
            record['had_force_recovery'] is not bool(events)):
        raise ValueError('Recovery accounting differs')
    by_id = {e['id']: [] for e in events}
    if len(by_id) != len(events): raise ValueError('Duplicate recovery event')
    previous = -1.
    for s in samples:
        t = _number(s['time_s'])
        if (s['event_id'] not in by_id or t <= previous or t > end_time_s + 1e-9 or
                abs(t-round(t/timestep)*timestep) > 1e-9):
            raise ValueError('Recovery native clock differs')
        previous = t
        for key in ('force_N','torque_G_Nm','penetration_m','linear_m_s','angular_rad_s'):
            if _number(s[key]) < 0: raise ValueError('Negative native magnitude')
        _number(s['position_z_m'])
        by_id[s['event_id']].append(s)
        if (s['linear_m_s']>.02 and 'SPEED_LIMIT' not in facts['motion_reasons']) or (
                s['angular_rad_s']>.5 and 'ANGULAR_SPEED_LIMIT' not in facts['motion_reasons']):
            raise ValueError('Native motion protection missing from historical facts')
    if events and (not samples or not _close(samples[0]['time_s'],events[0]['trigger_time_s']) or
            not _close(samples[-1]['time_s'],end_time_s) or
            any(not _close(b['time_s']-a['time_s'],timestep) for a,b in zip(samples,samples[1:]))):
        raise ValueError('Native force history must continue through final audit')
    native_cycles={}
    for s in samples:
        i=math.ceil(s['time_s']/control_period-1e-9)-1
        if not 0 <= i < len(cycle_peaks):raise ValueError('Native sample outside recorded cycles')
        native_cycles.setdefault(i,[]).append(s)
        for key in ('force_N','torque_G_Nm','penetration_m'):
            if key in cycle_peaks[i] and s[key]>cycle_peaks[i][key]+1e-10:
                raise ValueError('Native sample exceeds its saved cycle peak')
    for i,group in native_cycles.items():
        if len(group)==round(control_period/timestep):
            for key in ('force_N','torque_G_Nm','penetration_m'):
                if key in cycle_peaks[i] and not _close(max(s[key] for s in group),cycle_peaks[i][key]):
                    raise ValueError('Complete native cycle peak differs')
    last_end = -1.
    all_recovered = (not record['fatal_reasons'] and facts['simulation_valid'] and
        not facts['invalid_reasons'] and not facts['motion_reasons'] and
        set(facts['contact_reasons']).issubset({'FORCE_LIMIT'}))
    for e in events:
        start, end = _number(e['trigger_time_s']), _number(e['end_time_s'])
        group = [s for s in by_id[e['id']] if start-1e-9 <= s['time_s'] <= end+1e-9]
        if (not group or start <= last_end or end < start or end > end_time_s+1e-9 or
                not _close(group[0]['time_s'], start) or
                not _close(group[-1]['time_s'], end) or
                any(not _close(b['time_s']-a['time_s'], timestep) for a,b in zip(group,group[1:]))):
            raise ValueError('Incomplete native recovery interval')
        last_end = end
        event_peak = max(s['force_N'] for s in group)
        if not _close(event_peak, e['peak_force_N']) or group[0]['force_N'] <= 5.:
            raise ValueError('Recovery event peak/trigger differs')
        if e['status'] != 'COMPLETED':
            all_recovered = False
            continue
        if e.get('eligible') is not True or event_peak > 6. or end >= 30.:
            raise ValueError('Nonrecoverable guard claimed completed')
        over = [s for s in group if s['force_N'] > 5.]
        if (over[-1]['time_s']-start > .020+1e-9 or
                any(not _close(b['time_s']-a['time_s'],timestep) for a,b in zip(over,over[1:])) or
                not _close(e['last_over_force_time_s'],over[-1]['time_s']) or
                not _close(e['continuous_over_force_s'],over[-1]['time_s']-start)):
            raise ValueError('Long or repeated force event cannot recover')
        if any(s['torque_G_Nm'] > .1 or s['penetration_m'] > .00003 or
               s['linear_m_s'] > .020 or s['angular_rad_s'] > .5 for s in group):
            raise ValueError('Other native protection crossed during recovery')
        unload, retract, reached, resume = map(_number, (e['unloaded_time_s'],
            e['retract_start_time_s'], e['retracted_time_s'], e['resume_time_s']))
        if not (start < unload <= retract < reached < resume and _close(resume,end)):
            raise ValueError('Recovery stage time order differs')
        if (unload-start>wait_stable_s+control_period+1e-9 or
                reached-retract>recovery_time_limit_s+timestep+1e-9 or
                resume-reached>wait_stable_s+control_period+1e-9):
            raise ValueError('Recovery stage timeout exceeded')
        for s in group:
            moving = retract+1e-9 < s['time_s'] < reached-1e-9
            if s['phase'] != ('RETRACT' if moving else 'STOPPING'):
                raise ValueError('Native recovery phase differs')
            command=s['command_world']
            if (len(command)!=6 or any(abs(_number(command[i]))>1e-12 for i in (0,1,3,4,5)) or
                    not -.0005-1e-12 <= _number(command[2]) <= 1e-12 or
                    (not moving and abs(command[2])>1e-12)):
                raise ValueError('Recovery command exceeds deterministic retraction')
        def at(time):
            found = [s for s in group if _close(s['time_s'],time)]
            if len(found)!=1: raise ValueError('Missing recovery boundary sample')
            return found[0]
        def stable_tail(time, lower):
            tail=[s for s in group if time-.1-1e-9 <= s['time_s'] <= time+1e-9]
            if (not tail or tail[0]['time_s'] < lower-1e-9 or
                    not _close(tail[0]['time_s'],time-.1) or
                    any(s['force_N'] > .5 or s['penetration_m'] >= .00003 or s['linear_m_s'] > 1e-5 or
                        s['angular_rad_s'] > .001 for s in tail)):
                raise ValueError('Missing continuous low-load stable 100ms')
        stable_tail(unload,start)
        stable_tail(resume,reached)
        z0=at(retract)['position_z_m']; z1=at(reached)['position_z_m']
        if (not _close(z0,e['retract_start_z_m']) or z0-z1 < .00025-1e-12 or
                not _close(z0-z1,e['actual_retraction_m']) or
                z0-at(resume)['position_z_m'] < .00025-1e-12):
            raise ValueError('Actual 250um recovery displacement missing')
    if completed == len(events) and not record['fatal_reasons']:
        # Every original over-force cycle needs its own supporting native sample.
        for i,p in enumerate(cycle_peaks):
            if p['force_N'] <= 5.: continue
            group=[s for s in samples if i*control_period+1e-9 < s['time_s'] <= (i+1)*control_period+1e-9]
            if not group or not _close(max(s['force_N'] for s in group),p['force_N']):
                raise ValueError('Unaccounted native force peak')
            if any(s['force_N'] > 5. and not any(
                    e['trigger_time_s']-1e-9 <= s['time_s'] <= e['end_time_s']+1e-9
                    for e in events) for s in group):
                raise ValueError('Force peak outside registered recovery')
    if peak > 5. and not events: raise ValueError('Missing recovery event')
    return dict(verified=True, all_force_events_recovered=all_recovered,
        had_force_recovery=bool(events), force_recovery_count=len(events),
        completed_force_recovery_count=completed, peak_force_N=peak,
        native_recovery_samples=len(samples), event_ids=[e['id'] for e in events],
        recovery_events=[{k:e.get(k) for k in ('id','status','end_time_s','status_reason')} for e in events])
