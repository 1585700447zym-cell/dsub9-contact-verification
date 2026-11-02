@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0tmp\learning_cpu_20260924\Scripts\python.exe" -I -B -X utf8 "%~dp0tools\usage\report_demo.py" %*
if errorlevel 1 (
  echo Demo failed. Please keep the error message above.
  pause
)
