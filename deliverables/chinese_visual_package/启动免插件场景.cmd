@echo off
setlocal
chcp 65001 >nul
set "PYTHON_EXE=D:\KEYANRUJIAN\python.exe"
set "PROJECT_ROOT=%~dp0..\.."

if not exist "%PYTHON_EXE%" (
  echo [错误] 找不到指定的 Python：%PYTHON_EXE%
  echo 请在本文件中修改 PYTHON_EXE，使其指向已安装 MuJoCo 的 python.exe。
  pause
  exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m tools.visualization.launch_viewer --mode polygon32 %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo.
  echo 免插件 polygon32 场景启动失败，请阅读上方中文提示。
  pause
)
exit /b %EXIT_CODE%
