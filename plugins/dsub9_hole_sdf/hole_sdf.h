#ifndef DSUB9_HOLE_SDF_H_
#define DSUB9_HOLE_SDF_H_

#include <mujoco/mjplugin.h>
#include <mujoco/mjtype.h>

#if defined(_WIN32)
#define DSUB9_HOLE_EXPORT extern "C" __declspec(dllexport)
#else
#define DSUB9_HOLE_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace dsub9::hole_sdf {

inline constexpr char kPluginName[] = "mujoco.sdf.dsub9_hole";
inline constexpr int kAttributeCount = 5;
inline constexpr const char* kAttributeNames[kAttributeCount] = {
    "bore_radius", "entry_radius", "entry_depth", "bore_depth", "outer_radius"};

struct HoleParams {
  mjtNum bore_radius;
  mjtNum entry_radius;
  mjtNum entry_depth;
  mjtNum bore_depth;
  mjtNum outer_radius;
};

bool Validate(const HoleParams& params);
mjtNum Distance(const mjtNum point[3], const HoleParams& params);
void Gradient(mjtNum gradient[3], const mjtNum point[3], const HoleParams& params);
bool RegisterPlugin();

}  // namespace dsub9::hole_sdf

DSUB9_HOLE_EXPORT int dsub9_register_plugin();
DSUB9_HOLE_EXPORT int dsub9_hole_validate(const mjtNum params[5]);
DSUB9_HOLE_EXPORT mjtNum dsub9_hole_distance(const mjtNum point[3],
                                             const mjtNum params[5]);
DSUB9_HOLE_EXPORT void dsub9_hole_gradient(mjtNum gradient[3], const mjtNum point[3],
                                           const mjtNum params[5]);

#endif  // DSUB9_HOLE_SDF_H_
