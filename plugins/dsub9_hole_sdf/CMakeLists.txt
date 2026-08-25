cmake_minimum_required(VERSION 3.24)
project(dsub9_hole_sdf LANGUAGES CXX)

if(NOT DEFINED MUJOCO_ROOT)
  message(FATAL_ERROR "Set MUJOCO_ROOT to the installed Python mujoco package directory")
endif()

cmake_path(ABSOLUTE_PATH MUJOCO_ROOT NORMALIZE OUTPUT_VARIABLE MUJOCO_ROOT_ABS)
set(MUJOCO_INCLUDE_DIR "${MUJOCO_ROOT_ABS}/include")
if(NOT EXISTS "${MUJOCO_INCLUDE_DIR}/mujoco/mjplugin.h")
  message(FATAL_ERROR "MuJoCo plugin headers not found under ${MUJOCO_INCLUDE_DIR}")
endif()
if(WIN32 AND NOT EXISTS "${MUJOCO_ROOT_ABS}/mujoco.dll")
  message(FATAL_ERROR "mujoco.dll not found under ${MUJOCO_ROOT_ABS}")
endif()

add_library(dsub9_hole_sdf SHARED hole_sdf.cc register.cc)
target_include_directories(dsub9_hole_sdf PRIVATE "${MUJOCO_INCLUDE_DIR}")
target_compile_features(dsub9_hole_sdf PRIVATE cxx_std_17)
set_target_properties(dsub9_hole_sdf PROPERTIES
  CXX_EXTENSIONS OFF
  OUTPUT_NAME "dsub9_hole_sdf"
)

if(MSVC)
  target_compile_options(dsub9_hole_sdf PRIVATE /W4 /permissive- /EHsc)
else()
  target_compile_options(dsub9_hole_sdf PRIVATE -Wall -Wextra -Wpedantic)
  if(UNIX AND NOT APPLE)
    target_link_libraries(dsub9_hole_sdf PRIVATE dl)
  endif()
endif()
