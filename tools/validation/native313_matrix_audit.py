"""Stop-event clock and lossless JSON tags for invalid floating-point evidence."""
import math


def actual_stop_start(events, decision_time):
    start=None
    phase=None
    for e in events:
        current=e.get('phase')
        if current is None:continue
        if current=='STOPPING':
            if phase!='STOPPING':start=float(e['time_s'])
        else:start=None
        phase=current
    return start


def samples_finite(rows):
    return all(isinstance(r.get(k),(int,float)) and math.isfinite(r[k])
               for r in rows for k in ('time_s','linear_m_s','angular_rad_s'))


def actual_stop_pass(rows, events, decision_time, end_time, timestep):
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    start=actual_stop_start(events,decision_time)
    if start is None or not samples_finite(rows) or end_time<start+2.-1e-9:return False
    deadline=start+2.
    bounded=[r for r in rows if r['time_s']<=deadline+timestep/2]
    return bool(physical_tail_pass(bounded,deadline,timestep))


def archive_nonfinite(value):
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite':str(value)}
    if isinstance(value,dict):return {k:archive_nonfinite(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [archive_nonfinite(v) for v in value]
    return value
