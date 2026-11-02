@echo off
setlocal
pushd "%~dp0"
echo Opening the female 3D model...
echo Left drag: rotate. Wheel: zoom. Right drag: pan. Close the window to exit.
"tmp\learning_cpu_20260924\Scripts\python.exe" -B -X utf8 "deliverables\visual_usage\female_viewer_20261029\view_female.py" %*
set "TASK_EXIT=%ERRORLEVEL%"
popd
if not "%TASK_EXIT%"=="0" pause
exit /b %TASK_EXIT%
