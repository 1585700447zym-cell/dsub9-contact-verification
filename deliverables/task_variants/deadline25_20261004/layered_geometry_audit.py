"""Read-only analytic support audit for a cylinder clipped to each bore layer.

No changed referee, no physics stepping, and no relabeling of recorded outcomes.
The convex256 bore consists of tangent planes at n dot (p-hole_center)=radius.
Linear support on a clipped cylinder is attained on cap rims or on the cylinder
side at a slab boundary. Each such curve is an affine image of a circle; its
maximum is at the sinusoid optimum or a clipping endpoint.
"""
from pathlib import Path
import sys,json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.clearance_task import _pin_centers,_pin_sizes,pin_clearance_m

angles=np.arange(256)*2*np.pi/256
normals=np.c_[np.cos(angles),np.sin(angles),np.zeros(256)]

def intersections(a,b,k):
    r=math.hypot(a,b)
    if r<1e-18 or abs(k)>r+1e-15:return []
    phi=math.atan2(b,a);delta=math.acos(np.clip(k/r,-1,1))
    return [phi-delta,phi+delta]

def radial_extrema(c,a,b):
    # d||c+a*cos(theta)+b*sin(theta)||^2/dtheta = 0,
    # with tan(theta/2) giving a quartic. Include theta=pi explicitly.
    A=float(c@b);B=float(-c@a);C=float((b@b-a@a)/2);D=float(a@b)
    coefficients=np.array([D-A,2*B-4*C,-6*D,2*B+4*C,A+D])
    if np.max(np.abs(coefficients))<1e-30:return [0.,np.pi]
    roots=np.roots(coefficients/np.max(np.abs(coefficients)))
    return [0.,np.pi]+[2*math.atan(float(x.real)) for x in roots if abs(x.imag)<1e-8]

def layer_margin(center,rotation,radius,half,zlo,zhi,hole_xy,bore_radius):
    axis=rotation[:,2];assert axis[2]>.99
    a=radius*rotation[:,0];b=radius*rotation[:,1]
    # Endpoints common to cap rims and layer cuts.
    edge=[]
    for t in [-half,half]:
        for z in [zlo,zhi]:edge+=intersections(a[2],b[2],z-center[2]-axis[2]*t)
    candidates=[]
    for kind,value in [('cap',-half),('cap',half),('cut',zlo),('cut',zhi)]:
        if kind=='cap':p0=center+axis*value;aa=a;bb=b
        else:
            p0=center+axis*((value-center[2])/axis[2])
            aa=a-axis*(a[2]/axis[2]);bb=b-axis*(b[2]/axis[2])
        theta=np.r_[np.arctan2(normals@bb,normals@aa),edge,
                    radial_extrema(p0[:2]-hole_xy,aa[:2],bb[:2])]
        if not len(theta):continue
        if kind=='cap':ts=np.full(len(theta),value)
        else:ts=(value-center[2]-a[2]*np.cos(theta)-b[2]*np.sin(theta))/axis[2]
        points=p0+np.outer(np.cos(theta),aa)+np.outer(np.sin(theta),bb)
        good=(ts>=-half-1e-14)&(ts<=half+1e-14)&(points[:,2]>=zlo-1e-14)&(points[:,2]<=zhi+1e-14)
        candidates.extend(points[good])
    if not candidates:return dict(overlaps=False,margin_um=None)
    points=np.array(candidates);relative=points-np.r_[hole_xy,0.]
    support=relative@normals.T;i,j=np.unravel_index(np.argmax(support),support.shape)
    radii=np.linalg.norm(relative[:,:2],axis=1);k=int(np.argmax(radii))
    return dict(overlaps=True,margin_um=float((bore_radius-support[i,j])*1e6),
        circular_margin_um=float((bore_radius-radii[k])*1e6),circular_witness_world_m=points[k].tolist(),
        point_world_m=points[i].tolist(),face_index=int(j),face_normal=normals[j].tolist())

def rotation(row):
    w,x,y,z=np.array(row['quaternion_wxyz'])/np.linalg.norm(row['quaternion_wxyz'])
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def audit(row):
    rot=rotation(row);out=[]
    for i,(p,size) in enumerate(zip(_pin_centers,_pin_sizes)):
        center=rot@p+row['position_m']
        for name,r,z0,z1 in [('entry',.000675,0.,.00025),('main',.0006,.00025,.0045)]:
            result=layer_margin(center,rot,size[0],size[1],z0,z1,p[:2],r)
            out.append(dict(pin_index=i,layer=name,**result))
    return dict(old_full_shaft_margin_um=pin_clearance_m(row)*1e6,
        exact_circular_layer_margin_um=min(x['circular_margin_um'] for x in out if x['overlaps']),
        exact_polygon_layer_margin_um=min(x['margin_um'] for x in out if x['overlaps']),per_pin_layer=out)

# Independent zero-step analytic sanity checks.
I=np.eye(3)
assert abs(layer_margin(np.array([0,0,.002]),I,.0005,.002,.00025,.0045,[0,0],.0006)['margin_um']-100)<1e-9
assert abs(layer_margin(np.array([.000101,0,.002]),I,.0005,.002,.00025,.0045,[0,0],.0006)['margin_um']+1)<1e-9
assert layer_margin(np.array([0,0,-.004]),I,.0005,.002,.00025,.0045,[0,0],.0006)['overlaps'] is False
# Tilted lower end lies outside a narrow slab, so clipping must change margin.
theta=.007;R=np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]])
p=np.array([.000089,0,.002]);narrow=layer_margin(p,R,.0005,.002,.00025,.0035,[0,0],.0006)
whole=layer_margin(p,R,.0005,.002,-.01,.01,[0,0],.0006)
assert narrow['margin_um']>whole['margin_um']+3

d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));e=d['summary'];rows=d['trace']
at=lambda t:min(rows,key=lambda r:abs(r['time_s']-t))
results={name:audit(row) for name,row in [('stop',at(e['stop_time'])),('after_0.2s',at(e['stop_time']+.2)),('task_end',at(e['task_end_time'])),('final',rows[-1])]}
record=dict(scope='Offline pin-only analytic cylinder support against actual 256-sided entry/main bore layers; unchanged recorded verdict',
    sanity_checks=4,no_new_physics=True,old_referee_preserved=True,samples=results)
(OUT/'layered_geometry_audit.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:{n:v[n] for n in ['old_full_shaft_margin_um','exact_polygon_layer_margin_um','exact_circular_layer_margin_um']} for k,v in results.items()}))
