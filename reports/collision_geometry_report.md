# D-sub9 collision geometry and contact validation

## Scope and interpretation

The formal model is `models/dsub9_pair.xml` with nine analytic circular-hole SDF geoms.  The 32-sided
hole model is retained only as a comparison fallback at `build/dsub9_pair_polygon32.xml`.  Contact output
is a numerical diagnostic for this rigid-contact model: **real insertion force is uncalibrated**.  No value
in Newtons or Newton-metres is an acceptance threshold for hardware.

The male task origin starts at world Z = -4.0 mm for insertion cases and moves along +world Z.  The reported
depth obeys `male_origin_world_z_m = start_origin_z_m + final_depth_m`; therefore 4.0 mm depth places the male
and female task origins at the same Z.  The runner prescribes poses with zero velocity and calls MuJoCo
forward/constraint solving at every pose.  It is a deterministic quasi-static pose sweep, not a force
controller, reinforcement-learning policy, or free-dynamics integration.

## Source integrity, bounds, and transform

All bounds below were freshly read from binary STL triangles or STEP `VERTEX_POINT` references.  Units are
millimetres.

| File | SHA-256 | Minimum | Maximum |
| --- | --- | --- | --- |
| `DSub9_Deliverables_V4/DSub9_Female_Refined_V3.STL` | `13b9329e214a07abe3d1346072572cad03b2374c455125ba56a6f3c7cce6cbbd` | `[0, 0, ~0]` | `[30.7999992, 12.5500002, 9.7000008]` |
| `DSub9_Deliverables_V4/DSub9_Female_Refined_V3.step` | `8afb66c2ecbab8b02be06b59a4cd726c29ed949be3c354f3233bf7595d7eb39f` | `[-15.4, -6.275, 0]` | `[15.4, 6.275, 9.7]` |
| `DSub9_Deliverables_V4/DSub9_Male_TwoStageRearShell_V3.step` | `e6b3c453c5066ab18e3c594c53a21ee006f6c9030e9e8ee17b4274d2e26ad44a` | `[-15.4, -7, -22]` | `[15.4, 7, 4]` |
| `assets/visual/dsub9_female_visual_centered.stl` | `c37b549a7db371d39388b9109889efb525eb2182f3cd520d07c51add16ffe065` | `[-15.3999996, -6.2750001, ~0]` | `[15.3999996, 6.2750001, 9.7000008]` |
| `assets/visual/dsub9_male_visual_centered.stl` | `e2d0ce38faee11f4d00acee74155983719f36830984d186d3838f6bf28f1d153` | `[-15.3999996, -7, -22]` | `[15.3999996, 7, 4]` |

The female source STL is translated exactly `[-15.4, -6.275, 0] mm`; it is not scaled or rotated.  The male
STL uses the STEP task frame directly.  MuJoCo imports all STL assets with scale `0.001 0.001 0.001`.

The male STL was exported by SOLIDWORKS Premium 2023 SP5.0/build 31.5.0.0052 as binary millimetre STL,
custom resolution, 0.01 mm maximum chord deviation, 5 degree maximum angle tolerance, default coordinate
system, and with “Do not translate STL output data to positive space” checked.  The verified export contains
3,932 triangles and is 196,684 bytes.  The earlier positive-space export was rejected.

## Collision representations

The male uses nine analytic cylinders, diameter 1.00 mm and length 4.00 mm, on the reviewed 5+4 array
(2.77 mm column pitch and 2.84 mm row-centre separation).  The female holes share those exact centres.

The D-shaped CAD walls are convex decompositions of actual z = 0.5 mm sections.  The selected male outer
and inner loops contain 156 and 177 points, with bounding boxes 16.456263 x 8.300000 mm and
15.099202 x 6.900000 mm.  The selected female outer and inner loops each contain 84 points, with bounding
boxes 19.727337 x 9.500000 mm and 16.681988 x 8.600000 mm.  Arc-aware decomposition produces 78 male
guide pieces over z = 0–4.0 mm and 42 female socket pieces over z = 0–4.5 mm, exactly 120 D pieces.  Their
projected union areas are 30.033554 mm² and 46.753580 mm² respectively.  Visual meshes have collision
disabled.

The exact pin/hole centres in millimetres are the five-point upper row
`(-5.540, 1.420), (-2.770, 1.420), (0, 1.420), (2.770, 1.420), (5.540, 1.420)` and the four-point lower
row `(-4.155, -1.420), (-1.385, -1.420), (1.385, -1.420), (4.155, -1.420)`.  Every pin is a 1.00 mm
diameter analytic cylinder spanning local z = 0–4.00 mm.  Every formal hole is active, uses the same centre,
and has the dimensions below; collision bitmasks permit all nine pin↔hole pairs while filtering same-side
and cross-feature contacts.

The analytic hole is the revolution of the counter-clockwise stepped material polygon in `(r,z)`:

```
(entry_radius, 0)
(outer_radius, 0)
(outer_radius, bore_depth)
(bore_radius, bore_depth)
(bore_radius, entry_depth)
(entry_radius, entry_depth)
```

Distance magnitude is the minimum Euclidean point-to-segment distance and its sign is negative inside the
material, positive in free bore space.  The gradient points toward increasing signed distance.  Parameters
are bore radius 0.575 mm, entry radius 0.675 mm, entry depth 0.25 mm, bore depth 4.50 mm, and local outer
radius 1.00 mm.  The main diameter is 1.15 mm, entry diameter 1.35 mm, and nominal radial pin-hole clearance
is 0.075 mm.

The fallback contains 9 holes × 2 axial layers × 32 sectors = 576 closed convex meshes.  Its circumscribed
main-hole boundary has 0.002782179 mm maximum radial error, about 3.71% of nominal radial clearance.  It is
explicitly labelled `polygon32` fallback and is not used as the formal model.

| Inventory | Formal SDF | polygon32 fallback |
| --- | ---: | ---: |
| Bodies / free joints | 3 / 1 | 3 / 1 |
| Geoms | 140 | 707 |
| Mesh assets | 123 | 698 |
| Plugin instances | 1 | 0 |
| Pins / holes | 9 / 9 analytic SDF | 9 / 576 sector meshes |
| Male / female D pieces | 78 / 42 | 78 / 42 |

Formal model SHA-256 is `31e5ffb9e9e692c8e0f85354a9ff247b187c8bfc5a701b92b816936d09c03acd`.
Fallback XML SHA-256 is `b17e52ccdeca16626fa267ac76d01d8e38b44e614822e277c0f1fba45037d2cd`.
The tested Release plugin SHA-256 is `a3516dd4e488ec2be8db4a5082fa96c37e3f6ea1cebb7a74341b3edc0d325278`.

## Contact wrench and numerical settings

MuJoCo 3.9.0 was used.  The plugin was explicitly loaded in a fresh runner process from project-root cwd
through the ASCII relative path `build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll`; fallback validation does
not load or depend on the DLL.

For every contact, `mj_contactForce` returns a contact-frame wrench on geom2.  The runner transforms it with
`contact.frame.T`; it keeps that sign when male is geom2 and negates it when male is geom1.  It adds
`(contact_position - male_task_origin) × force` to the transformed contact torque.  All results are therefore
the wrench acting on the male body, expressed in world/task-aligned axes, about the male task origin.
Component peaks retain the sign at that component's maximum absolute value.

Case orientation is `R = Ry(pitch) @ Rx(roll)`: for column vectors, roll acts first and pitch acts second.
An independent basis-vector test locks this order.  At actual roll and combined contact poses, an independent
per-contact accumulation matches runner output and MuJoCo generalized constraint force: translation compares
directly with `qfrc_constraint[:3]`, while torque compares with
`R_body @ qfrc_constraint[3:6]`.  The tolerance is 1e-12 absolute and 1e-10 relative, below the smallest
reported diagnostic torque.  The reviewed Task5 model uses the default three-dimensional contact, so local
torsional contact-force slots are zero in these static poses; the independently verified world torque includes
the nonzero `(contact_position - male_task_origin) × force` term.

A separate deterministic transform fixture supplies a nontrivial orthonormal contact frame, nonzero local
force, nonzero local torque, and a nonzero lever arm.  It independently checks male-as-geom2 and male-as-geom1
signs.  Removing the transformed local-torque term changes the expected world moment and fails this test,
while the real Task5 fixed-pose tests continue to anchor the zero-local-torque, nonzero-`r × F` case.

A controlled sphere-plane probe gave +259.3195 N along the contact normal on geom2 and exactly the same
free-body `qfrc_constraint`; the real D-sub9 probe, where pins are geom1, matched `qfrc_constraint` only after
using the corresponding negative sign.  This evidence, plus the symmetric offset and tilt cases below,
guards against a guessed or globally flipped sign.

The default sweep uses MuJoCo Newton solver with 100 iterations, timestep 0.0002 s, prescribed speed
0.05 m/s, and spatial increment 10 µm.  The fine combined case uses timestep 0.0001 s and 5 µm increments.
Because pose is assigned directly before `mj_forward`, the sensitivity comparison changes both the solver
timestep and spatial sampling; it is not a comparison of free-body dynamics integration.

The only termination values are `SUCCESS`, `EXCESS_PENETRATION`, and `NUMERICAL_ERROR`.
Maximum penetration is `max(0, -contact.dist)` over actual contacts.  The 30 µm limit is 40% of the 75 µm
nominal radial clearance and terminates before gross overlap.  Any non-finite pose, constraint force, contact
distance, wrench, penetration, or result produces `NUMERICAL_ERROR`.  A prescribed pose cannot be stopped by
contact, so no stalled-progress outcome is exposed.  Such an outcome belongs in a future force-controlled or
free-dynamics runner where commanded and achieved motion can diverge.

## Actual contact results

These values are from `reports/contact_validation_results.json`, generated by the runner.  Force and torque
are uncalibrated diagnostics, not correctness gates.

| Case | Mode | Termination | Depth mm | Max contacts | Max penetration µm | Primary signed component | Steps | Runtime s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| separated | SDF | SUCCESS | 0.000 | 0 | 0.000 | — | 1 | 0.0002 |
| aligned | SDF | SUCCESS | 4.000 | 0 | 0.000 | — | 401 | 0.5210 |
| X +100 µm | SDF | SUCCESS | 4.000 | 54 | 12.011 | Fx -1.818e-3 N | 401 | 0.8448 |
| X -100 µm | SDF | SUCCESS | 4.000 | 81 | 12.039 | Fx +2.036e-3 N | 401 | 1.1425 |
| Y +100 µm | SDF | SUCCESS | 4.000 | 72 | 12.425 | Fy -1.985e-3 N | 401 | 1.2076 |
| Y -100 µm | SDF | SUCCESS | 4.000 | 63 | 12.352 | Fy +1.736e-3 N | 401 | 0.8749 |
| roll +1.5° | SDF | SUCCESS | 4.000 | 63 | 13.528 | Tx -6.624e-6 N·m | 401 | 0.6570 |
| roll -1.5° | SDF | SUCCESS | 4.000 | 63 | 13.668 | Tx +7.978e-6 N·m | 401 | 0.7584 |
| pitch +1.5° | SDF | SUCCESS | 4.000 | 30 | 14.231 | Ty -1.115e-5 N·m | 401 | 0.7453 |
| pitch -1.5° | SDF | SUCCESS | 4.000 | 51 | 14.007 | Ty +7.678e-6 N·m | 401 | 0.8227 |
| combined A | SDF | EXCESS_PENETRATION | 0.180 | 7 | 31.894 | Tx -1.532e-5 N·m | 19 | 0.0280 |
| combined B | SDF | EXCESS_PENETRATION | 0.260 | 15 | 30.802 | Tx +1.333e-5 N·m | 27 | 0.0417 |
| combined A fine | SDF | EXCESS_PENETRATION | 0.180 | 7 | 31.894 | Tx -1.532e-5 N·m | 37 | 0.0539 |
| aligned | polygon32 | SUCCESS | 4.000 | 0 | 0.000 | — | 401 | 0.1099 |
| X +100 µm | polygon32 | SUCCESS | 4.000 | 267 | 24.976 | Fx -3.898e-3 N | 401 | 2.6618 |
| combined A | polygon32 | EXCESS_PENETRATION | 0.110 | 15 | 38.244 | Tx -6.878e-6 N·m | 12 | 0.0034 |

Separated has zero contacts and aligned reaches the full 4.0 mm with finite state.  Both X and Y offset
pairs oppose the commanded offset.  Both tilt pairs have opposite primary torque signs.  Coarse/fine
combined A share termination and Tx sign.  SDF/fallback +X share negative Fx; combined A shares negative Tx.
Different contact counts, penetration and runtime are expected from analytic sampling versus 576 polygon
sectors.  The early-terminating combined fallback runtime is not a full-depth performance comparison.

## Reproduction and observed limits

Commands executed from the project root with `D:\KEYANRUJIAN\python.exe` in the normal Windows environment:

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m tools.validation.run_contact_cases --all --output reports/contact_validation_results.json
# 16 results; schema 2; tracked LF SHA-256 9108a3cf67322b3225b7ba07d2045c3e3cc76a53bfe49d92ac435829f8f823fe

& 'D:\KEYANRUJIAN\python.exe' -m pytest -q -W error -p no:cacheprovider --basetemp 'tmp\pytest-task7-final'
# 128 passed: the previous 121 tests plus 7 reporting/manifest tests; zero skips

& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest
& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest --verify
```

The restricted Codex runner produced 98 passes and 23 SDF-plugin-test failures when MSBuild was denied access
to user-local Windows SDK metadata (`MSB4184`).  The same source and test command in a normal Windows process
built the Release DLL and ran the complete 128-test suite with zero skips and `-W error`.  The command above
uses a project-local pytest temporary directory only to avoid unrelated ACLs left by isolated processes; it
does not inject, replace, or skip tests.  Ordinary users should run the direct README commands in a normal
Visual Studio/Windows SDK environment and should not copy any temporary pytest injector.

The runner result cache was removed.  Two independent fresh processes each ran the complete 16-result matrix;
all termination and physical fields matched exactly after removing `runtime_s`.  Wall-clock values are
deliberately excluded from that comparison because natural timing differences are not a reliable freshness
assertion.  Immutable compiled model resources remain cached, but every `run_case` creates new `MjData`,
executes the complete sweep, and measures that execution.

The runtime freshness regression uses a controlled internal clock with intervals `[10,11.25]` and
`[20,22.5]`; two calls must return distinct objects with identical physical fields and runtimes 1.25 s and
2.5 s after exactly four clock calls.  A temporary mutation restoring result caching makes this test fail on
object identity and stale runtime, proving it detects the rejected implementation rather than relying on
wall-clock jitter.

The formal SDF remains the primary representation.  polygon32 contact multiplicity and force magnitude are
not interchangeable with SDF values.  Rigid geometry plus uncalibrated MuJoCo contact parameters cannot
represent socket spring contacts, material nonlinearity, friction calibration, wear, or real hardware safety
limits.  In particular, **real insertion force is uncalibrated**.

## Final reviewed-file manifest

`reports/final_file_manifest.txt` is generated by `tools.reporting.generate_manifest`, not by shell
redirection.  It covers every reviewed regular file under `assets/`, `models/`, `plugins/`, `tools/`,
`tests/`, and `reports/`, plus `README.md`, `pyproject.toml`, `.gitattributes`, and `.gitignore`.  Entries use lowercase
SHA-256 and sorted POSIX project-relative paths.  Build outputs and ignored cache/temporary/SDD-ledger files
are outside that reviewed set; the tested DLL hash is recorded above.  The manifest necessarily excludes
`reports/final_file_manifest.txt` itself, because including its own digest would create an unsatisfiable
self-reference.  `--verify` recomputes every other entry and fails if a reviewed file is missing, added, or
changed.

Raw-byte SHA-256 reproducibility also depends on checkout normalization.  Before the fix, the repository had
no `.gitattributes`; an external-index `core.autocrlf=true` Windows checkout changed 32 reviewed text files
to CRLF and `--verify` failed, even though the manifest reader accepted either line ending for the manifest
itself.  The root rule `* text=auto eol=lf` now keeps reviewed text at LF on checkout, while `*.stl binary`
prevents any STL filtering.  A real temporary external Git directory plus `checkout-index` regression runs
the verifier inside the fresh checkout and independently requires zero hash mismatches and unchanged STL
bytes.  Applying that policy changed only line endings in the three tracked model XML files and contact JSON;
their parsed structure, geometry, contact fields, and Git-normalized content are unchanged.  The formal-model
and tracked contact-JSON hashes above are therefore the LF byte hashes used by the reviewed manifest.
The immutable ASCII STEP sources are an intentional exception: `text eol=crlf` preserves their reviewed
source hashes without changing the Git-normalized blobs, while SLDPRT files are binary.
