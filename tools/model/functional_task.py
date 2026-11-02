"""Functional rigid insertion referee; precision is a separate reported metric."""
import numpy as np

from tools.model.clearance_task import pin_fit

TASK_ID = 'dsub9_clearance120_functional_v2'


def functional_finish(row, criteria):
    """One qualifying sample; the common session enforces hold and guard priority.

    No artificial XY/angle limits: all nine full pin shafts must fit their bores.
    Depth is the connector reference plane, not an electrical contact assertion.
    """
    p=np.asarray(row['position_m']);v=np.asarray(row['velocity_world'])
    w=np.asarray(row['contact_wrench_G']);q=np.asarray(row['quaternion_wxyz'])
    if p.shape!=(3,) or v.shape!=(6,) or w.shape!=(6,) or q.shape!=(4,):
        return False
    if not np.isfinite(np.r_[p,v,w,q,row['penetration_m']]).all():
        return False
    return bool(abs(p[2])<=criteria['z_tolerance_m'] and pin_fit(row)
                and np.linalg.norm(v[:3])<=criteria['linear_speed_m_s']
                and np.linalg.norm(v[3:])<=criteria['angular_speed_rad_s']
                and np.linalg.norm(w[:3])<criteria['force_N']
                and np.linalg.norm(w[3:])<criteria['torque_Nm']
                and row['penetration_m']<criteria['penetration_m'])
