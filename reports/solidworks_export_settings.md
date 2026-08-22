# SolidWorks male visual STL export settings

## Source and application

- Source: `DSub9_Deliverables_V4/DSub9_Male_TwoStageRearShell_V3.step`.
- Application window: `SOLIDWORKS Premium 2023 SP5.0`.
- Installed executable: `D:\Program Files\SOLIDWORKS Corp2023\SOLIDWORKS\SLDWORKS.exe`.
- Reported file build: `31.5.0.0052`; installed-product registration: `2023 SP05 / 31.150.0052`.

## Final export settings actually used

- Save-as type and options-page file format: `STL (*.stl)` / `STL`.
- Output: binary.
- Units: millimetres.
- Resolution: custom.
- Maximum chord deviation: `0.01 mm`.
- Maximum angle tolerance: `5.00000 degrees`.
- Output coordinate system: `-- Default --`; no manual coordinate transform was applied.
- `Do not translate STL output data to positive space` was checked (Chinese UI: `不要转换 STL 输出数据到正坐标空间(I)`).
- `Show STL info before saving` was checked; preview and maximum facet size were not enabled.

## Export verification

The final information dialog reported 3,932 triangles, 196,684 bytes, and binary output.  The resulting
`assets/visual/dsub9_male_visual_centered.stl` has bounds
`min [-15.3999996, -7.0, -22.0] mm`, `max [15.3999996, 7.0, 4.0] mm`.

An earlier export without the positive-space-preservation checkbox was rejected: it had bounds
`min [0.0, 0.0, 0.0] mm`, `max [30.8, 14.0, 26.0] mm`.  This was a SolidWorks export-space option, not a
CAD geometry edit; the rejected derived file was overwritten only after the corrected export passed validation.
