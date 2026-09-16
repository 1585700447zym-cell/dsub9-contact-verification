"""Bounded virtual Cartesian drive. Only reset prescribes the actual pose.

This is the dynamic actuator validation layer, not an admittance controller or
Gym training environment. All limits and inertial values are uncalibrated.
"""
from dataclasses import dataclass, asdict
import math
import mujoco
import numpy as np

from tools.model.contact_development import build_xml
from tools.validation.run_contact_cases import _project_root_cwd, _quaternion
from tools.dynamics.safety import limit_command, shift_wrench


@dataclass(frozen=True)
class DynamicConfig:
    collision_backend: str = 'mpr'
    timestep: float = .0002
    control_period: float = .002
    linear_speed: float = .001
    angular_speed: float = .03
    linear_acceleration: float = .005
    angular_acceleration: float = .3
    translational_stiffness: float = 100.
    rotational_stiffness: float = .02
    force_limit_N: float = .05
    torque_limit_Nm: float = .002
    reference_lead_m: float = .0002
    reference_lead_rad: float = .03
    stop_force_N: float = .025
    stop_torque_Nm: float = .0005
    stop_penetration_m: float = 30e-6
    invalid_penetration_m: float = 80e-6
    actual_speed_limit: float = .02
    actual_angular_speed_limit: float = .5
    travel_limit_m: float = .006
    recovery_distance_m: float = .00025
    recovery_speed: float = .0005
    recovery_time_limit_s: float = 1.
    recovery_force_N: float = .01
    stopped_speed: float = 1e-5
    stopped_angular_speed: float = .001

    def __post_init__(self):
        if self.collision_backend not in ('mpr','native'):
            raise ValueError('Unknown collision backend')
        if any(not math.isfinite(v) or v <= 0 for k,v in asdict(self).items() if k!='collision_backend'):
            raise ValueError('All dynamic parameters must be finite and positive')
        ratio=self.control_period/self.timestep
        if ratio<1 or abs(ratio-round(ratio))>1e-10:
            raise ValueError('Control period must contain an integer number of physical steps')
        if self.invalid_penetration_m<=self.stop_penetration_m:
            raise ValueError('Invalid penetration must exceed stop threshold')
        if self.recovery_force_N>=self.stop_force_N or self.recovery_speed>self.linear_speed:
            raise ValueError('Recovery must stay within the operating limits')


class CartesianEnvironment:
    def __init__(self, config=None, segments=128, contacts_enabled=True):
        self.config=config or DynamicConfig()
        with _project_root_cwd():
            self.model=mujoco.MjModel.from_xml_string(build_xml(segments))
        self.model.opt.timestep=self.config.timestep
        if self.config.collision_backend=='mpr':
            self.model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)
        if not contacts_enabled:
            self.model.geom_contype[:]=0;self.model.geom_conaffinity[:]=0
        self.data=mujoco.MjData(self.model)
        self.male=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,'male')
        if self.model.nv!=6 or np.any(self.model.jnt_limited) or self.model.neq:
            raise ValueError('Fast wrench measurement requires one unconstrained free body')
        if np.any(self.model.body_ipos[self.male]) or np.any(self.model.dof_frictionloss):
            raise ValueError('Contact wrench shortcut requires COM at M and no joint friction')
        self.grasp_local=np.array([0.,0.,-.0145])
        self.kp=np.array([self.config.translational_stiffness]*3+[self.config.rotational_stiffness]*3)
        mass=self.model.body_mass[self.male]
        self.kd=2*np.sqrt(self.kp*np.r_[[mass]*3,self.model.body_inertia[self.male]])
        self.velocity_limits=np.array([self.config.linear_speed]*3+[self.config.angular_speed]*3)
        self.acceleration_limits=np.array([self.config.linear_acceleration]*3+[self.config.angular_acceleration]*3)
        self.effort_limits=np.array([self.config.force_limit_N]*3+[self.config.torque_limit_Nm]*3)
        self.phase='UNINITIALIZED'
        self.segments=segments;self.contacts_enabled=contacts_enabled

    def reset(self, case, *, allow_initial_contact=False):
        values=[case.x_offset_m,case.y_offset_m,case.start_origin_z_m,case.roll_rad,case.pitch_rad]
        if not np.isfinite(values).all(): raise ValueError('Initial pose must be finite')
        mujoco.mj_resetData(self.model,self.data)
        self.data.qpos[:]=(*values[:3],*_quaternion(case))
        self.reference=self.data.qpos.copy();self.initial=self.data.qpos.copy()
        self.command=np.zeros(6);self.raw_command=np.zeros(6);self.drive=np.zeros(6)
        self.events=[];self.phase='RUNNING';self.recovery_count=0;self.physical_steps=0
        self.peaks={'force_N':0.,'torque_G_Nm':0.,'penetration_m':0.,'speed_m_s':0.,
                    'drive_force_components_N':[0.,0.,0.], 'drive_torque_components_Nm':[0.,0.,0.],
                    'contact_count':0}
        self.drive_saturation_steps=0;self.command_limited_steps=0;self.reference_limited_steps=0
        self.first_contact=None;self.stop_snapshot=None;self.recovery_start=None
        mujoco.mj_forward(self.model,self.data)
        if not self._state_valid():
            self._terminate('INVALID_INITIAL_STATE');raise ValueError('Invalid initial simulation state')
        row=self._read()
        if (row['penetration_m']>1e-9 or row['contact_count']) and not allow_initial_contact:
            self.phase='TERMINAL'
            raise ValueError('Initial contact is not allowed for ordinary approach episodes')
        self.last_finite=row
        self._record_peaks(row)
        return row

    def _read(self):
        r=self.data.xmat[self.male].reshape(3,3)
        # No other constraints are present: translational generalized constraint
        # forces are world F, free-joint rotational ones are body-local torque.
        wrench=np.r_[self.data.qfrc_constraint[:3],r@self.data.qfrc_constraint[3:]]
        p=self.data.xpos[self.male].copy();g=p+r@self.grasp_local
        velocity=np.r_[self.data.qvel[:3],r@self.data.qvel[3:]]
        penetration=max(0.,-float(np.min(self.data.contact.dist))) if self.data.ncon else 0.
        return {'time_s':float(self.data.time),'position_m':p.tolist(),'quaternion_wxyz':self.data.qpos[3:].tolist(),
                'velocity_world':velocity.tolist(),'contact_wrench_M':wrench.tolist(),
                'contact_wrench_G':shift_wrench(wrench,p,g).tolist(),'penetration_m':penetration,
                'contact_count':self.data.ncon,'phase':self.phase,'reference_qpos':self.reference.tolist(),
                'raw_command_world':self.raw_command.tolist(),'limited_command_world':self.command.tolist(),
                'drive_wrench_M':self.drive.tolist()}

    def observe(self):
        if self.phase=='UNINITIALIZED':raise RuntimeError('Reset first')
        return dict(self.last_finite,phase=self.phase)

    def _record_peaks(self,row):
        force=float(np.linalg.norm(row['contact_wrench_M'][:3]))
        torque=float(np.linalg.norm(row['contact_wrench_G'][3:]))
        for key,value in [('force_N',force),('torque_G_Nm',torque),('penetration_m',row['penetration_m']),
                          ('speed_m_s',np.linalg.norm(row['velocity_world'][:3])),('contact_count',row['contact_count'])]:
            self.peaks[key]=max(self.peaks[key],float(value))
        self.peaks['drive_force_components_N']=np.maximum(self.peaks['drive_force_components_N'],abs(self.drive[:3])).tolist()
        self.peaks['drive_torque_components_Nm']=np.maximum(self.peaks['drive_torque_components_Nm'],abs(self.drive[3:])).tolist()
        if row['contact_count'] and self.first_contact is None:
            self.first_contact={'time_s':row['time_s'],'position_m':row['position_m']}

    def _terminate(self,reason):
        self.phase='TERMINAL';self.command[:]=0;self.data.qfrc_applied[:]=0
        self.events.append({'time_s':float(self.data.time),'reason':reason,'phase':'TERMINAL'})

    def _state_valid(self):
        return (math.isfinite(self.data.time) and
                all(np.isfinite(x).all() for x in (self.data.qpos,self.data.qvel,self.data.qacc,
                    self.data.qfrc_constraint,self.data.xpos,self.data.xmat,self.data.contact.dist)) and
                not any(w.number for w in self.data.warning))

    def stop(self,reason='REQUESTED_STOP'):
        if self.phase in ('TERMINAL','UNINITIALIZED'):raise RuntimeError('No active episode')
        if self.phase=='STOPPING':return
        self.phase='STOPPING';self.reference=self.data.qpos.copy();self.command[:]=0
        self.stop_snapshot={'time_s':float(self.data.time),'position_m':self.data.qpos[:3].tolist(),
                            'velocity_world':self.last_finite['velocity_world']}
        self.events.append({'time_s':float(self.data.time),'reason':reason,'phase':'STOPPING'})

    def request_recovery(self):
        if not self._state_valid():
            self._terminate('INVALID_SIMULATION');raise RuntimeError('Live state invalid for recovery')
        c=self.config;row=self.observe()
        if (self.phase!='STOPPING' or self.recovery_count>=1 or
            np.linalg.norm(row['velocity_world'][:3])>c.stopped_speed or
            np.linalg.norm(row['velocity_world'][3:])>c.stopped_angular_speed or
            np.linalg.norm(row['contact_wrench_M'][:3])>c.recovery_force_N or
            np.linalg.norm(row['contact_wrench_G'][3:])>c.stop_torque_Nm or
            row['penetration_m']>=c.stop_penetration_m):
            raise RuntimeError('Recovery preconditions not met')
        if np.linalg.norm(self.data.qpos[:3]-self.initial[:3])+c.recovery_distance_m>c.travel_limit_m:
            raise RuntimeError('Insufficient travel allowance for recovery')
        self.phase='RETRACT';self.recovery_count+=1;self.recovery_start=self.data.qpos.copy()
        self.recovery_start_time=float(self.data.time)
        self.reference=self.data.qpos.copy();self.command[:]=0
        self.events.append({'time_s':float(self.data.time),'reason':'RECOVERY_ACCEPTED','phase':self.phase})

    def _guard(self,row):
        c=self.config
        if (not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all() or
            not np.isfinite(self.data.qacc).all() or not np.isfinite(row['contact_wrench_G']).all() or
            any(w.number for w in self.data.warning)):
            self._terminate('INVALID_SIMULATION');return
        if row['penetration_m']>c.invalid_penetration_m:
            self._terminate('INVALID_PENETRATION');return
        if (np.linalg.norm(row['velocity_world'][:3])>c.actual_speed_limit or
            np.linalg.norm(row['velocity_world'][3:])>c.actual_angular_speed_limit or
            np.linalg.norm(self.data.qpos[:3]-self.initial[:3])>c.travel_limit_m):
            self._terminate('OUT_OF_BOUNDS');return
        if self.phase not in ('RUNNING','RETRACT'):return
        reasons=[]
        if row['penetration_m']>c.stop_penetration_m:reasons.append('PENETRATION_LIMIT')
        if np.linalg.norm(row['contact_wrench_M'][:3])>c.stop_force_N:reasons.append('FORCE_LIMIT')
        if np.linalg.norm(row['contact_wrench_G'][3:])>c.stop_torque_Nm:reasons.append('TORQUE_LIMIT')
        if reasons:self.stop('+'.join(reasons))

    def step(self, command_world):
        if self.phase in ('UNINITIALIZED','TERMINAL'):raise RuntimeError('No active episode')
        if not self._state_valid():
            self._terminate('INVALID_SIMULATION');return self.observe()
        try:
            requested=np.asarray(command_world,dtype=float)
        except (ValueError,TypeError,OverflowError) as error:
            self._terminate('INVALID_COMMAND');raise ValueError('Command conversion failed') from error
        if requested.shape!=(6,) or not np.isfinite(requested).all():
            self._terminate('INVALID_COMMAND');raise ValueError('Command must be finite shape6')
        self.raw_command=requested.copy()
        if self.phase=='STOPPING':requested=np.zeros(6)
        if self.phase=='RETRACT':requested=np.array([0,0,-self.config.recovery_speed,0,0,0])
        limited=limit_command(requested,self.command,self.config.control_period,
                              self.velocity_limits,self.acceleration_limits)
        if not np.allclose(limited,requested,rtol=0,atol=1e-15):self.command_limited_steps+=1
        self.command=limited
        for _ in range(round(self.config.control_period/self.config.timestep)):
            # Advance only the command reference; actual pose is integrated below.
            target_r=np.zeros(9);mujoco.mju_quat2Mat(target_r,self.reference[3:])
            reference_velocity=np.r_[self.command[:3],target_r.reshape(3,3).T@self.command[3:]]
            mujoco.mj_integratePos(self.model,self.reference,reference_velocity,self.config.timestep)
            error=np.zeros(6);mujoco.mj_differentiatePos(self.model,error,1.,self.data.qpos,self.reference)
            limits=np.array([self.config.reference_lead_m]*3+[self.config.reference_lead_rad]*3)
            clipped=np.clip(error,-limits,limits)
            if not np.array_equal(error,clipped):
                self.reference_limited_steps+=1;self.reference=self.data.qpos.copy()
                mujoco.mj_integratePos(self.model,self.reference,clipped,1.)
            r=self.data.xmat[self.male].reshape(3,3)
            error_world=np.r_[clipped[:3],r@clipped[3:]]
            velocity=np.r_[self.data.qvel[:3],r@self.data.qvel[3:]]
            raw=self.kp*error_world+self.kd*(self.command-velocity)
            self.drive=np.clip(raw,-self.effort_limits,self.effort_limits)
            if not np.array_equal(raw,self.drive):self.drive_saturation_steps+=1
            p=self.data.xpos[self.male];g=p+r@self.grasp_local
            at_g=shift_wrench(self.drive,p,g)
            self.data.qfrc_applied[:]=0
            mujoco.mj_applyFT(self.model,self.data,at_g[:3],at_g[3:],g,self.male,self.data.qfrc_applied)
            try:
                mujoco.mj_step(self.model,self.data)
                mujoco.mj_forward(self.model,self.data)
            except mujoco.FatalError:
                self._terminate('SIMULATION_ERROR');break
            self.physical_steps+=1
            if not self._state_valid():
                self._terminate('INVALID_SIMULATION');break
            row=self._read()
            if np.isfinite(self.data.qpos).all() and np.isfinite(self.data.qvel).all() and np.isfinite(row['contact_wrench_G']).all():
                self.last_finite=row;self._record_peaks(row)
            self._guard(row)
            if self.phase=='TERMINAL':break
            if self.phase=='RETRACT' and self.recovery_start[2]-self.reference[2]>=self.config.recovery_distance_m:
                self.stop('RECOVERY_DISTANCE_REACHED')
            if self.phase=='RETRACT' and self.data.time-self.recovery_start_time>=self.config.recovery_time_limit_s:
                self.stop('RECOVERY_TIME_LIMIT')
        return self.observe()

    def metadata(self):
        return {'config':asdict(self.config),'segments':self.segments,'contacts_enabled':self.contacts_enabled,
                'effective_options':{'timestep':self.model.opt.timestep,'disableflags':int(self.model.opt.disableflags),
                                     'ccd_tolerance':self.model.opt.ccd_tolerance,'ccd_iterations':self.model.opt.ccd_iterations,
                                     'integrator':int(self.model.opt.integrator)},
                'mass_kg':float(self.model.body_mass[self.male]),'inertia_kg_m2':self.model.body_inertia[self.male].tolist(),
                'grasp_local_m':self.grasp_local.tolist(),'measurement':'simulation_contact_wrench',
                'calibrated':False,'drive':'bounded_cartesian_PD_at_M_equivalent_wrench_applied_at_G'}
