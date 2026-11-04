"""Bind native stop mathematics to the saved physical event, not decision time."""
import math
from tools.learning.five_axis_preparation import _auditor

VERSION='native_event_stop_clock_v1'
GUARDS={'FORCE_LIMIT','TORQUE_LIMIT','PENETRATION_LIMIT','SPEED_LIMIT',
        'ANGULAR_SPEED_LIMIT','TRAVEL_LIMIT','ROTATION_LIMIT'}


def verify_stopping_interval(raw,receipt,dt,control_period,*,recovery_proof=None):
    decision=receipt['stop_time_s'];start=event=None;phase=None
    for e in raw['events']:
        current=e.get('phase')
        if current is None:continue
        if current=='STOPPING':
            if phase!='STOPPING':start=e['time_s'];event=e
        else:start=event=None
        phase=current
    if start is None or phase!='STOPPING':
        raise ValueError('A final physical STOPPING event is required')
    for value in (decision,start,dt,control_period):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Finite stop clock required')
    if dt<=0 or control_period<=0:raise ValueError('Positive native/control periods required')
    markers=[e for e in raw['events'] if e.get('reason')=='RECOVERY_FINAL_AUDIT_START'
             and e['time_s'] >= start]
    epoch=None
    if markers:
        marker=markers[-1];epoch=marker['time_s']
        if (len(markers)!=1 or recovery_proof is None or recovery_proof.get('verified') is not True or
                marker.get('physical_stop_preserved') is not True or
                abs(marker.get('physical_stop_time_s',-1)-start)>1e-9 or
                abs(epoch-decision)>1e-9 or epoch<start or receipt['audit_end_time_s']<epoch+2.-1e-9):
            raise ValueError('Unqualified final recovery audit epoch')
        linked=[e for e in recovery_proof.get('recovery_events',[]) if e['id']==marker.get('force_recovery_id')]
        if marker.get('recovery_kind')=='force':
            if (len(linked)!=1 or linked[0]['status'] not in ('FATAL','ABORTED') or
                    not 0 <= epoch-linked[0]['end_time_s'] <= control_period+1e-9 or
                    (linked[0]['status']=='ABORTED' and linked[0]['status_reason']!=marker.get('decision_reason'))):
                raise ValueError('Final audit epoch lacks its failed force recovery')
        elif marker.get('recovery_kind')=='normal':
            if (event.get('reason') not in ('B2_SEARCH_EXHAUSTED','RECOVERY_DISTANCE_REACHED') or
                    (linked and linked[0]['status']!='COMPLETED') or
                    marker.get('recovery_count')!=sum(e.get('reason')=='RECOVERY_ACCEPTED' and e['time_s']<=epoch for e in raw['events'])):
                raise ValueError('Final audit epoch lacks its normal recovery')
        else: raise ValueError('Unknown final recovery audit kind')
    lag=decision-start
    if lag < -1e-8 or (epoch is None and lag > control_period+1e-8):
        raise ValueError('Stop decision must follow its physical event within one control cycle')
    if epoch is None and lag > 1e-8 and not (set(event.get('reason','').split('+')) & GUARDS):
        raise ValueError('Intra-cycle stop-clock offset requires an explicit native hard guard')
    if abs(start-round(start/dt)*dt)>1e-8 or abs(decision-round(decision/control_period)*control_period)>1e-8:
        raise ValueError('Stop clock is off its native/control sample grid')
    # The archived trace/events/samples and all physical thresholds stay intact.
    # Only the private stop-math argument uses the physical event origin.
    proof=_auditor()._stop_math(raw,dict(receipt,stop_time_s=start),dt,control_period)
    proof.update(clock_version=VERSION,decision_time_s=decision,physical_start_time_s=start,
                 decision_lag_s=lag)
    if epoch is not None:
        # The old check verifies the entire unbroken physical STOPPING segment.
        # This additionally requires a fresh two seconds after the final decision.
        final=[s for s in raw['stop_samples'] if s['time_s']>epoch+dt/2]
        tail=[s for s in final if epoch+1.9-dt/2 <= s['time_s'] <= epoch+2.+dt/2]
        if (len(final)!=round((receipt['audit_end_time_s']-epoch)/dt) or
                len(tail)!=round(.1/dt)+1 or
                any(s['linear_m_s']>1e-5 or s['angular_rad_s']>.001 for s in tail)):
            raise ValueError('Final recovery audit lacks its native stable tail')
        proof.update(final_audit_start_time_s=epoch,final_audit_native_samples=len(final))
    return proof
