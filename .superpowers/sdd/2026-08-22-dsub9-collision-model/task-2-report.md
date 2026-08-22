# Task 2 report — centred visual STL assets

## Status

DONE

## RED/GREEN evidence

- RED: `D:\KEYANRUJIAN\Scripts\pytest.exe tests\mesh\test_visual_assets.py -v` first collected two tests and both
  failed with `FileNotFoundError` for the missing derived female and male STL assets.
- A subsequent RED run after the first SolidWorks export rejected the male bounds `min [0, 0, 0]`,
  `max [30.8, 14, 26]`; the two validation tests also initially failed because `validate_male_export` did not exist.
- GREEN: `D:\KEYANRUJIAN\python.exe -m tools.mesh.normalize_visual_meshes --validate-male
  assets\visual\dsub9_male_visual_centered.stl` accepted the corrected export.
- GREEN: `D:\KEYANRUJIAN\Scripts\pytest.exe tests\mesh\test_visual_assets.py -v` completed with `4 passed`.

The test/runtime executable was `D:\KEYANRUJIAN\python.exe` (Python 3.13.5); pytest was 8.3.4.  No packages
were installed.

## Generated assets

| Asset | Minimum (mm) | Maximum (mm) |
| --- | --- | --- |
| `assets/visual/dsub9_female_visual_centered.stl` | `[-15.3999996, -6.2750001, ~0]` | `[15.3999996, 6.2750001, 9.7000008]` |
| `assets/visual/dsub9_male_visual_centered.stl` | `[-15.3999996, -7.0, -22.0]` | `[15.3999996, 7.0, 4.0]` |

The female normalisation applies exactly `[-15.4, -6.275, 0] mm` only after checking the raw source size, and
recalculates each normal from the translated triangle vertices before writing the binary STL.  Male validation
explicitly rejects both thousand-fold scale and wrong-origin meshes.

## SolidWorks export

See `reports/solidworks_export_settings.md`.  The actual application was SolidWorks Premium 2023 SP5.0;
the executable build was 31.5.0.0052 and the installed-product registration was 2023 SP05 / 31.150.0052.
The first default export was rejected because SolidWorks translated its STL output to positive space.  The final
export used the checked `Do not translate STL output data to positive space` option and no manual coordinate
transform.

## Changed files

- `tools/mesh/normalize_visual_meshes.py`
- `tests/mesh/test_visual_assets.py`
- `assets/visual/dsub9_female_visual_centered.stl`
- `assets/visual/dsub9_male_visual_centered.stl`
- `reports/solidworks_export_settings.md`
- `.superpowers/sdd/2026-08-22-dsub9-collision-model/task-2-report.md`

## Commit

Implementation and assets commit: `bd3a09465ca5f437e650f146d41aa291153ad55c` (task-scoped).

## Concerns

No remaining acceptance concern.  The rejected intermediate male STL was a derived asset only and was replaced
after successful validation; no file under `DSub9_Deliverables_V4/` was modified.
