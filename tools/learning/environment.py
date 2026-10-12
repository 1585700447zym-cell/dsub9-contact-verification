"""Instance-local sampling with the frozen dynamics and guard behavior unchanged.

This compatibility class does not implement the new v3 motion guard and must
not be used to claim training admission.
"""
import numpy as np
from .runtime import ROOT, verify_runtime, active_package

verify_runtime(active_package())
from tools.dynamics.contact_candidate import NativeTightCandidate


class SampledCompatibilityEnvironment(NativeTightCandidate):
    def reset(self, case, *, allow_initial_contact=False):
        self.stop_samples = []
        self.begin_cycle()
        row = super().reset(case, allow_initial_contact=allow_initial_contact)
        self.begin_cycle()  # Initial forward is not a physical integration sample.
        return row

    def begin_cycle(self):
        self.cycle_peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0., samples=0)

    def _record_peaks(self, row):
        super()._record_peaks(row)
        for key, value in [('force_N', np.linalg.norm(row['contact_wrench_M'][:3])),
                           ('torque_G_Nm', np.linalg.norm(row['contact_wrench_G'][3:])),
                           ('penetration_m', row['penetration_m'])]:
            self.cycle_peaks[key] = max(self.cycle_peaks[key], float(value))
        self.cycle_peaks['samples'] += 1
        if self.phase == 'STOPPING':
            self.stop_samples.append(dict(time_s=float(self.data.time),
                                          linear_m_s=float(np.linalg.norm(self.data.qvel[:3])),
                                          angular_rad_s=float(np.linalg.norm(self.data.qvel[3:]))))
