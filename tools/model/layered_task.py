"""Versioned pin referee for the actual entry/main convex256 bore layers.

Geometry is a referee-only input. Historical all-shaft criteria remain intact.
Each finite cylinder is clipped to a layer's Z slab, then checked against all
tangent planes of that layer. The legacy 1 nm geometry tolerance is unchanged.
"""
import math
import numpy as np

from tools.model.clearance_task import _pin_centers,_pin_sizes,_source,BORE_RADIUS_M,SEGMENTS

TASK_ID='dsub9_clearance120_layered_25s_v4'
GEOMETRY_TOLERANCE_M=1e-9
_parameters={x.get('key'):float(x.get('value')) for x in _source.findall('.//extension/plugin/instance/config')}
_LAYERS=(('entry',_parameters['entry_radius'],0.,_parameters['entry_depth']),
         ('main',BORE_RADIUS_M,_parameters['entry_depth'],_parameters['bore_depth']))
_angles=np.arange(SEGMENTS)*2*math.pi/SEGMENTS
_normals=np.c_[np.cos(_angles),np.sin(_angles),np.zeros(SEGMENTS)]
_holes=np.array([[float(v) for v in x.get('pos').split()] for x in _source.findall('.//geom[@type="sdf"]')])
if _holes.shape!=(9,3) or not np.array_equal(_holes[:,:2],_pin_centers[:,:2]) or np.any(_holes[:,2]):
    raise ValueError('Layered task requires the bound nine-hole layout at Z=0')


def referee_metadata():
    return dict(id='clipped_cylinder_convex256_v1',tolerance_m=GEOMETRY_TOLERANCE_M,
                layers=[dict(name=n,radius_m=r,z0_m=a,z1_m=b) for n,r,a,b in _LAYERS],
                segments=SEGMENTS,minimum_axis_z=.99,requires_all_nine_main_overlaps=True)


def _boundary_angles(a,b,value):
    amplitude=math.hypot(a,b)
    if amplitude<1e-18 or abs(value)>amplitude+1e-15:return []
    phase=math.atan2(b,a);offset=math.acos(np.clip(value/amplitude,-1.,1.))
    return [phase-offset,phase+offset]


def _layer_margin(center,rotation,radius,half,zlo,zhi,hole_xy,bore_radius):
    """Minimum face clearance, or None if cylinder and slab do not meet.

    Linear support over a cylinder/slab intersection occurs on a cap rim or
    side/slab intersection. Each is an affine circle with a clipped angular
    domain: inspect the sinusoid optimum and every clipping endpoint.
    Caller guarantees near-vertical axis and finite, model-bound dimensions.
    """
    axis=rotation[:,2];a=radius*rotation[:,0];b=radius*rotation[:,1]
    edges=[]
    for t in [-half,half]:
        for z in [zlo,zhi]:edges+=_boundary_angles(a[2],b[2],z-center[2]-axis[2]*t)
    maximum=None
    for kind,value in [('cap',-half),('cap',half),('cut',zlo),('cut',zhi)]:
        if kind=='cap':origin=center+axis*value;aa=a;bb=b
        else:
            origin=center+axis*((value-center[2])/axis[2])
            aa=a-axis*(a[2]/axis[2]);bb=b-axis*(b[2]/axis[2])
        theta=np.r_[np.arctan2(_normals@bb,_normals@aa),edges]
        cosine=np.cos(theta);sine=np.sin(theta)
        axial=np.full(len(theta),value) if kind=='cap' else (value-center[2]-a[2]*cosine-b[2]*sine)/axis[2]
        points=origin+np.outer(cosine,aa)+np.outer(sine,bb)
        valid=(axial>=-half-1e-14)&(axial<=half+1e-14)&(points[:,2]>=zlo-1e-14)&(points[:,2]<=zhi+1e-14)
        if not np.any(valid):continue
        # Including other faces' optimum points is harmless: they are feasible.
        relative=points[valid]-np.r_[hole_xy,0.]
        support=float(np.max(relative@_normals.T))
        maximum=support if maximum is None else max(maximum,support)
    return None if maximum is None else bore_radius-maximum


def _pose(row):
    try:p=np.asarray(row['position_m'],dtype=float);q=np.asarray(row['quaternion_wxyz'],dtype=float)
    except (ValueError,TypeError,KeyError):return None
    if p.shape!=(3,) or q.shape!=(4,) or not np.isfinite(np.r_[p,q]).all() or not np.any(q):return None
    q=q/np.max(np.abs(q));q=q/np.linalg.norm(q);w,x,y,z=q
    rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                       [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                       [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    if rotation[2,2]<.99:return None
    return p,rotation


def layered_pin_clearance_m(row):
    pose=_pose(row)
    if pose is None:return -math.inf
    p,rotation=pose;minimum=math.inf
    for pin,size,hole in zip(_pin_centers,_pin_sizes,_holes):
        center=rotation@pin+p
        for name,radius,zlo,zhi in _LAYERS:
            margin=_layer_margin(center,rotation,size[0],size[1],zlo,zhi,hole[:2],radius)
            if margin is None:
                if name=='main':return -math.inf
                continue
            minimum=min(minimum,margin)
    return float(minimum)


def layered_pin_fit(row):
    return layered_pin_clearance_m(row)>=-GEOMETRY_TOLERANCE_M


def functional_finish(row,criteria):
    try:
        p=np.asarray(row['position_m']);q=np.asarray(row['quaternion_wxyz'])
        v=np.asarray(row['velocity_world']);w=np.asarray(row['contact_wrench_G']);penetration=row['penetration_m']
        if p.shape!=(3,) or q.shape!=(4,) or v.shape!=(6,) or w.shape!=(6,):return False
        if not np.isfinite(np.r_[p,q,v,w,penetration]).all():return False
        return bool(abs(p[2])<=criteria['z_tolerance_m']
            and np.linalg.norm(v[:3])<=criteria['linear_speed_m_s'] and np.linalg.norm(v[3:])<=criteria['angular_speed_rad_s']
            and np.linalg.norm(w[:3])<criteria['force_N'] and np.linalg.norm(w[3:])<criteria['torque_Nm']
            and penetration<criteria['penetration_m'] and layered_pin_fit(row))
    except (ValueError,TypeError,KeyError):return False
