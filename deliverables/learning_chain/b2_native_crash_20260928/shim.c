#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mujoco/mujoco.h>
#include "engine/engine_collision_gjk.h"

// Copied from the same pinned engine_collision_convex.c; not exported by the wheel.
void mjc_pointSupport(mjtNum res[3], mjCCDObj* obj, const mjtNum dir[3]) {
  for(int i=0;i<3;i++) res[i]=obj->pos[i];
}
void mjc_lineSupport(mjtNum res[3], mjCCDObj* obj, const mjtNum dir[3]) {
  const mjtNum* mat=obj->mat; const mjtNum* pos=obj->pos;
  mjtNum dot=mat[2]*dir[0]+mat[5]*dir[1]+mat[8]*dir[2];
  mjtNum scl=dot>=0?obj->size[1]:-obj->size[1];
  res[0]=mat[2]*scl+pos[0];res[1]=mat[5]*scl+pos[1];res[2]=mat[8]*scl+pos[2];
}

__declspec(dllexport) int diagnostic_pair(const mjModel* m, mjData* d, int g1, int g2) {
  mjCCDObj obj1, obj2;
  mjc_initCCDObj(&obj1, m, d, g1, 0);
  mjc_initCCDObj(&obj2, m, d, g2, 0);
  size_t size = mjc_ccdSize(m->npolygonmax, m->nmeshdegmax, m->opt.ccd_iterations);
  unsigned char* buffer = malloc(size + 4096);
  memset(buffer, 0xA5, size + 4096);
  mjCCDConfig config = {0};
  config.max_iterations=m->opt.ccd_iterations; config.tolerance=m->opt.ccd_tolerance;
  config.max_contacts=1; config.dist_cutoff=0; config.buffer=buffer;
  config.npolygonmax=m->npolygonmax; config.nmeshdegmax=m->nmeshdegmax;
  mjCCDStatus status = {0};
  printf("BEGIN buffer=%zu iterations=%d geom_types=%d,%d\n",size,config.max_iterations,obj1.geom_type,obj2.geom_type);
  fflush(stdout);
  double dist=mjc_ccd(&config,&status,&obj1,&obj2);
  int changed=0;
  for(size_t i=size;i<size+4096;i++) if(buffer[i]!=0xA5) changed++;
  printf("END dist=%.17g contacts=%d gjk=%d epa=%d overflow_bytes=%d\n",dist,status.nx,status.gjk_iterations,status.epa_iterations,changed);
  fflush(stdout);
  free(buffer);
  return changed;
}
