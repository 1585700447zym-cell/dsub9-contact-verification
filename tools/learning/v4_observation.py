"""Append sensed drive/search state to v1; never reuse old network dimensions."""
from copy import deepcopy
import numpy as np
from .observation import ObservationBuilder

class V4ObservationBuilder:
    version='residual_reference_whitelist_v4'
    def __init__(self,initial_state,config):
        self.base=ObservationBuilder(initial_state,config)
        self.config=config;self.schema=[];self.slices={}

    def capture(self,snapshot,context,*,refresh=False):
        vector,raw=self.base.capture(snapshot,context,refresh=refresh)
        values=vector.tolist();self.schema=deepcopy(self.base.schema);self.slices=deepcopy(self.base.slices)
        ctrl=snapshot.controller_state;row=snapshot.state;cfg=self.config
        def add(name,value,width=1,scale=1.,unit='1'):
            x=np.atleast_1d(np.asarray(value,dtype=float))
            if x.shape!=(width,) or not np.isfinite(x).all():raise ValueError('Invalid v4 observation: '+name)
            start=len(values);values.extend(np.clip(x/scale,-10,10).tolist());raw[name]=x.tolist()
            self.slices[name]=slice(start,len(values))
            self.schema.append(dict(name=name,start=start,width=width,scale=[scale]*width,unit=unit,source='relative_sensed_drive_or_controller'))
        ref=np.asarray(row['reference_qpos'][:3])-self.base.initial_position
        origin=ctrl['search_origin'];peak=ctrl['episode_peak_z_m'];progress=ctrl['search_progress_origin_z_m']
        add('relative_drive_reference_m',ref,3,.004,'m')
        add('search_reference_xy_m',[0,0] if origin is None else ref[:2]-np.asarray(origin)[:2],2,cfg.spiral_radius_m,'m')
        add('search_reference_valid',origin is not None)
        add('episode_peak_z_m',0 if peak is None else peak,scale=.004,unit='m');add('episode_peak_valid',peak is not None)
        displacement_z=row['position_m'][2]-self.base.initial_position[2]
        add('net_search_remaining_m',0 if progress is None else progress+cfg.search_exit_advance_m-displacement_z,scale=.004,unit='m')
        add('net_search_valid',progress is not None)
        for prefix,key,scale in [('rotation_risk','rotation_risk_since_s',.05),('search_load','search_load_since_s',.02)]:
            start=ctrl[key]
            if start is not None and not np.isfinite(start):raise ValueError('Nonfinite v4 timer')
            add(prefix+'_elapsed_s',0 if start is None else max(0,snapshot.time_s-start),scale=scale,unit='s')
            add(prefix+'_valid',start is not None)
        add('admittance_xy_rebase_count',ctrl['admittance_xy_rebase_count'])
        add('reference_release_pending',ctrl['reference_release_requested'])
        add('previous_reference_filter_fraction',context['previous_filter_fraction'])
        return np.asarray(values,dtype=np.float32),raw
