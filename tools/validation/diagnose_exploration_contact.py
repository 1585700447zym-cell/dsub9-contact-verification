"""Read-only localization of contact tracking losses from the four closed V1 archives."""
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation.run_exploration_execution import OUT as V1,read,write,sha,validate

OUT=ROOT/'deliverables/learning_chain/five_axis_execution_entropy_screen_20261026'


def analyze(raw,config):
    trace=raw['trace'];rows=raw['transitions'];groups={}
    command=np.array([r['limited_command_world'][:2] for r in trace[1:]])
    drive=np.array([r['drive_wrench_M'] for r in trace[1:]])
    reaction=np.array([r['contact_wrench_M'] for r in trace[1:]])
    actual=np.array([r['velocity_world'][:2] for r in trace[1:]])
    refs=np.array([r['reference_qpos'][:2] for r in trace])
    position=np.array([r['position_m'][:2] for r in trace])
    lead=refs[1:]-position[1:]
    nonintegral=abs(np.diff(refs,axis=0)-command*.002)>1e-9
    near_cap=abs(lead)>=config['reference_lead_m']-3e-6
    active=np.array([r['action_active'] for r in rows])
    phases=np.array([r['action_log']['composition_inputs']['phase'] for r in rows])
    contact=np.array([bool(r['contact_count']) for r in trace[1:]])
    interior=np.r_[False,active[:-1] & active[1:] & (phases[:-1]==phases[1:])]
    dn=np.linalg.norm(drive[:,:2],axis=1);cn=np.linalg.norm(reaction[:,:2],axis=1)
    balanced=np.linalg.norm(drive[:,:2]+reaction[:,:2],axis=1)<.1*(dn+cn)
    opposite=(drive[:,:2]*reaction[:,:2]).sum(axis=1)<0
    stalled=np.linalg.norm(actual,axis=1)<50e-6
    effort_limits=np.array([config['force_limit_N']]*3+[config['torque_limit_Nm']]*3)
    for name,mask in [('free',active & ~contact),('contact',active & contact),
                      ('search_contact',active & contact & (phases=='SEARCH'))]:
        if not mask.any():continue
        force_mask=mask & (dn>.1) & (cn>.1)
        interior_mask=mask & interior
        corrections=nonintegral & interior_mask[:,None]
        fraction=lambda x:float(np.mean(x[mask]))
        groups[name]=dict(cycles=int(mask.sum()),
            drive_sample_saturation_fraction=np.mean(abs(drive[mask])>=effort_limits-1e-9,axis=0).tolist(),
            maximum_abs_sampled_drive=abs(drive[mask]).max(axis=0).tolist(),
            mean_abs_drive_xy_N=abs(drive[mask,:2]).mean(axis=0).tolist(),
            mean_abs_contact_xy_N=abs(reaction[mask,:2]).mean(axis=0).tolist(),
            reaction_opposes_drive_fraction=float(opposite[force_mask].mean()) if force_mask.any() else None,
            force_balance_fraction=float(balanced[force_mask].mean()) if force_mask.any() else None,
            force_balance_and_slow_fraction=float((balanced & stalled)[force_mask].mean()) if force_mask.any() else None,
            nearly_stalled_fraction=fraction(stalled),
            reference_xy_near_cap_fraction=np.mean(near_cap[mask],axis=0).tolist(),
            interior_reference_correction_cycles=corrections.sum(axis=0).tolist(),
            corrections_near_cap_fraction=[float(np.mean(near_cap[corrections[:,a],a]))
                if corrections[:,a].any() else None for a in range(2)],
            active_search_reference_filter_cycles=sum(rows[i]['action_log']['reference_filter_fraction']<1.
                for i in np.flatnonzero(mask)))
    idx=np.flatnonzero(active & contact & balanced & stalled & (dn>.5) &
                       (np.linalg.norm(command,axis=1)>.0002))
    examples=[]
    for i in idx[::max(1,len(idx)//3)][:3]:
        examples.append(dict(time_s=trace[i+1]['time_s'],command_xy_um_s=(command[i]*1e6).tolist(),
            actual_xy_um_s=(actual[i]*1e6).tolist(),drive_xy_N=drive[i,:2].tolist(),
            contact_xy_N=reaction[i,:2].tolist(),reference_lead_xy_um=(lead[i]*1e6).tolist()))
    return dict(groups=groups,examples=examples,
        direct_full_request_damping_force_bound_N=config['linear_speed']*0 +
            read(V1/'registration.json')['common']['effective_kd'][0]*50e-6,
        twenty_ms_full_request_unclipped_position_force_bound_N=config['translational_stiffness']*50e-6*.020)


def main():
    reg=read(V1/'registration.json');validate(reg)
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir();results={};pins={}
    for job in reg['schedule']:
        path=V1/'run'/job['id']/'episode.json.gz'
        receipt=read(path.parent/'receipt.json')
        if sha(path)!=receipt['archive_sha256']:raise ValueError('Archive changed')
        pins[path.relative_to(ROOT).as_posix()]=sha(path)
        raw=json.loads(gzip.decompress(path.read_bytes()))
        results[job['id']]=analyze(raw,reg['common']['dynamic_config'])
    write(OUT/'contact_execution_diagnosis.json',dict(results=results,input_sha256=pins,
        simulation_initializations=0,physical_substeps=0,neural_inference=0,optimizer_updates=0,
        limitations=['drive/contact values are 2 ms endpoint samples, not all native substeps',
                     'correlations and force balance do not isolate friction versus geometric contact',
                     'a componentwise reference clip does not clear all other axes']))
    for name,r in results.items():print(name,json.dumps(r['groups'].get('search_contact'),ensure_ascii=False))


if __name__=='__main__':main()
