#include "hole_sdf.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace dsub9::hole_sdf {
namespace {

constexpr HoleParams kDefaults{0.000575, 0.000675, 0.00025, 0.00450, 0.00100};

struct DistanceGradient {
  mjtNum distance;
  std::array<mjtNum, 3> gradient;
};

struct MujocoApi {
  void (*default_plugin)(mjpPlugin*);
  int (*register_plugin)(const mjpPlugin*);
  const char* (*get_plugin_config)(const mjModel*, int, const char*);

  explicit operator bool() const {
    return default_plugin != nullptr && register_plugin != nullptr &&
           get_plugin_config != nullptr;
  }
};

template <typename Function>
Function ResolveSymbol(const char* name) {
#if defined(_WIN32)
  HMODULE module = GetModuleHandleW(L"mujoco.dll");
  if (module == nullptr) {
    return nullptr;
  }
  return reinterpret_cast<Function>(GetProcAddress(module, name));
#else
  return reinterpret_cast<Function>(dlsym(RTLD_DEFAULT, name));
#endif
}

const MujocoApi& Api() {
  static const MujocoApi api{
      ResolveSymbol<void (*)(mjpPlugin*)>("mjp_defaultPlugin"),
      ResolveSymbol<int (*)(const mjpPlugin*)>("mjp_registerPlugin"),
      ResolveSymbol<const char* (*)(const mjModel*, int, const char*)>(
          "mj_getPluginConfig"),
  };
  return api;
}

struct ProfilePoint {
  mjtNum radius;
  mjtNum z;
};

std::array<ProfilePoint, 6> ProfileVertices(const HoleParams& params) {
  return {{{params.entry_radius, 0},
           {params.outer_radius, 0},
           {params.outer_radius, params.bore_depth},
           {params.bore_radius, params.bore_depth},
           {params.bore_radius, params.entry_depth},
           {params.entry_radius, params.entry_depth}}};
}

bool InsideProfile(mjtNum radius, mjtNum z, const std::array<ProfilePoint, 6>& vertices) {
  bool inside = false;
  ProfilePoint previous = vertices.back();
  for (const ProfilePoint& current : vertices) {
    if ((current.z > z) != (previous.z > z)) {
      const mjtNum crossing_radius =
          current.radius +
          (z - current.z) * (previous.radius - current.radius) / (previous.z - current.z);
      if (radius < crossing_radius) {
        inside = !inside;
      }
    }
    previous = current;
  }
  return inside;
}

DistanceGradient StepProfile(const mjtNum point[3], const HoleParams& params) {
  const mjtNum radius = std::hypot(point[0], point[1]);
  const auto vertices = ProfileVertices(params);
  mjtNum best_squared_distance = std::numeric_limits<mjtNum>::infinity();
  mjtNum best_delta_radius = 0;
  mjtNum best_delta_z = 0;
  mjtNum best_outward_radius = 0;
  mjtNum best_outward_z = 0;

  for (std::size_t index = 0; index < vertices.size(); ++index) {
    const ProfilePoint& start = vertices[index];
    const ProfilePoint& end = vertices[(index + 1) % vertices.size()];
    const mjtNum edge_radius = end.radius - start.radius;
    const mjtNum edge_z = end.z - start.z;
    const mjtNum edge_squared_length = edge_radius * edge_radius + edge_z * edge_z;
    mjtNum projection = ((radius - start.radius) * edge_radius +
                         (point[2] - start.z) * edge_z) /
                        edge_squared_length;
    projection = std::clamp(projection, mjtNum{0}, mjtNum{1});
    const mjtNum closest_radius = start.radius + projection * edge_radius;
    const mjtNum closest_z = start.z + projection * edge_z;
    const mjtNum delta_radius = radius - closest_radius;
    const mjtNum delta_z = point[2] - closest_z;
    const mjtNum squared_distance = delta_radius * delta_radius + delta_z * delta_z;
    // Strict comparison makes the first edge win exact ties in both implementations.
    if (squared_distance < best_squared_distance) {
      const mjtNum edge_length = std::sqrt(edge_squared_length);
      best_squared_distance = squared_distance;
      best_delta_radius = delta_radius;
      best_delta_z = delta_z;
      best_outward_radius = edge_z / edge_length;
      best_outward_z = -edge_radius / edge_length;
    }
  }

  const mjtNum unsigned_distance = std::sqrt(best_squared_distance);
  const bool inside = InsideProfile(radius, point[2], vertices);
  DistanceGradient result{inside ? -unsigned_distance : unsigned_distance, {0, 0, 0}};
  mjtNum gradient_radius;
  mjtNum gradient_z;
  if (unsigned_distance > 0) {
    const mjtNum sign = inside ? -1 : 1;
    gradient_radius = sign * best_delta_radius / unsigned_distance;
    gradient_z = sign * best_delta_z / unsigned_distance;
  } else {
    gradient_radius = best_outward_radius;
    gradient_z = best_outward_z;
  }
  if (radius > 0) {
    result.gradient[0] = gradient_radius * point[0] / radius;
    result.gradient[1] = gradient_radius * point[1] / radius;
  }
  result.gradient[2] = gradient_z;
  return result;
}

HoleParams FromArray(const mjtNum params[5]) {
  return HoleParams{params[0], params[1], params[2], params[3], params[4]};
}

std::array<mjtNum, kAttributeCount> ToArray(const HoleParams& params) {
  return {params.bore_radius, params.entry_radius, params.entry_depth, params.bore_depth,
          params.outer_radius};
}

bool ParseNumber(const char* text, mjtNum* output) {
  if (text == nullptr || text[0] == '\0') {
    return false;
  }
  errno = 0;
  char* end = nullptr;
  const double value = std::strtod(text, &end);
  while (end != nullptr && *end == ' ') {
    ++end;
  }
  if (end == text || end == nullptr || *end != '\0' || errno == ERANGE ||
      !std::isfinite(value)) {
    return false;
  }
  *output = static_cast<mjtNum>(value);
  return std::isfinite(*output);
}

bool ReadInstanceParams(const mjModel* model, int instance, HoleParams* params) {
  const MujocoApi& api = Api();
  if (!api) {
    return false;
  }
  *params = kDefaults;
  auto values = ToArray(*params);
  for (int index = 0; index < kAttributeCount; ++index) {
    const char* text = api.get_plugin_config(model, instance, kAttributeNames[index]);
    if (text != nullptr && text[0] != '\0' && !ParseNumber(text, &values[index])) {
      return false;
    }
  }
  *params = FromArray(values.data());
  return Validate(*params);
}

void ParseStaticAttributes(mjtNum attributes[], const char* names[], const char* values[]) {
  auto parsed = ToArray(kDefaults);
  for (int item = 0; item < kAttributeCount; ++item) {
    int destination = -1;
    for (int index = 0; index < kAttributeCount; ++index) {
      if (names[item] != nullptr && std::strcmp(names[item], kAttributeNames[index]) == 0) {
        destination = index;
        break;
      }
    }
    if (destination >= 0 && values[item] != nullptr && values[item][0] != '\0' &&
        !ParseNumber(values[item], &parsed[destination])) {
      parsed[destination] = std::numeric_limits<mjtNum>::quiet_NaN();
    }
  }
  if (!Validate(FromArray(parsed.data()))) {
    parsed.fill(std::numeric_limits<mjtNum>::quiet_NaN());
  }
  std::copy(parsed.begin(), parsed.end(), attributes);
}

}  // namespace

bool Validate(const HoleParams& params) {
  const auto values = ToArray(params);
  return std::all_of(values.begin(), values.end(),
                     [](mjtNum value) { return std::isfinite(value); }) &&
         0 < params.bore_radius && params.bore_radius < params.entry_radius &&
         params.entry_radius < params.outer_radius && 0 < params.entry_depth &&
         params.entry_depth < params.bore_depth;
}

mjtNum Distance(const mjtNum point[3], const HoleParams& params) {
  return StepProfile(point, params).distance;
}

void Gradient(mjtNum gradient[3], const mjtNum point[3], const HoleParams& params) {
  const DistanceGradient result = StepProfile(point, params);
  std::copy(result.gradient.begin(), result.gradient.end(), gradient);
}

bool RegisterPlugin() {
  const MujocoApi& api = Api();
  if (!api) {
    return false;
  }
  mjpPlugin plugin;
  api.default_plugin(&plugin);
  plugin.name = kPluginName;
  plugin.capabilityflags |= mjPLUGIN_SDF;
  plugin.nattribute = kAttributeCount;
  plugin.attributes = kAttributeNames;
  plugin.nstate = +[](const mjModel*, int) { return 0; };
  plugin.init = +[](const mjModel* model, mjData* data, int instance) {
    HoleParams params{};
    if (!ReadInstanceParams(model, instance, &params)) {
      return -1;
    }
    HoleParams* stored = new (std::nothrow) HoleParams(params);
    if (stored == nullptr) {
      return -1;
    }
    data->plugin_data[instance] = reinterpret_cast<std::uintptr_t>(stored);
    return 0;
  };
  plugin.destroy = +[](mjData* data, int instance) {
    delete reinterpret_cast<HoleParams*>(data->plugin_data[instance]);
    data->plugin_data[instance] = 0;
  };
  plugin.reset = +[](const mjModel*, mjtNum*, void*, int) {};
  plugin.compute = +[](const mjModel*, mjData*, int, int) {};
  plugin.sdf_distance = +[](const mjtNum point[3], const mjData* data, int instance) {
    const auto* params = reinterpret_cast<const HoleParams*>(data->plugin_data[instance]);
    return Distance(point, *params);
  };
  plugin.sdf_gradient = +[](mjtNum gradient[3], const mjtNum point[3], const mjData* data,
                            int instance) {
    const auto* params = reinterpret_cast<const HoleParams*>(data->plugin_data[instance]);
    Gradient(gradient, point, *params);
  };
  plugin.sdf_staticdistance = +[](const mjtNum point[3], const mjtNum* attributes) {
    return Distance(point, FromArray(attributes));
  };
  plugin.sdf_attribute = +[](mjtNum attributes[], const char* names[], const char* values[]) {
    ParseStaticAttributes(attributes, names, values);
  };
  plugin.sdf_aabb = +[](mjtNum aabb[6], const mjtNum* attributes) {
    const HoleParams params = FromArray(attributes);
    aabb[0] = 0;
    aabb[1] = 0;
    aabb[2] = params.bore_depth / 2;
    aabb[3] = params.outer_radius;
    aabb[4] = params.outer_radius;
    aabb[5] = params.bore_depth / 2;
  };
  return api.register_plugin(&plugin) >= 0;
}

}  // namespace dsub9::hole_sdf

int dsub9_register_plugin() {
  return dsub9::hole_sdf::RegisterPlugin() ? 1 : 0;
}

int dsub9_hole_validate(const mjtNum params[5]) {
  if (params == nullptr) {
    return 0;
  }
  const dsub9::hole_sdf::HoleParams converted{params[0], params[1], params[2], params[3],
                                               params[4]};
  return dsub9::hole_sdf::Validate(converted) ? 1 : 0;
}

mjtNum dsub9_hole_distance(const mjtNum point[3], const mjtNum params[5]) {
  const dsub9::hole_sdf::HoleParams converted{params[0], params[1], params[2], params[3],
                                               params[4]};
  return dsub9::hole_sdf::Distance(point, converted);
}

void dsub9_hole_gradient(mjtNum gradient[3], const mjtNum point[3],
                         const mjtNum params[5]) {
  const dsub9::hole_sdf::HoleParams converted{params[0], params[1], params[2], params[3],
                                               params[4]};
  dsub9::hole_sdf::Gradient(gradient, point, converted);
}
