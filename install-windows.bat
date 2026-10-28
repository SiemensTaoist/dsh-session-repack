@echo off
chcp 65001 >nul
setlocal

REM DSH 会话重压 —— 一键挂成计划任务（Windows）
REM 用法：把本文件和 repack.py 放在同一目录，双击运行

set SCRIPT_DIR=%~dp0
set PY=python
set THRESHOLD=20

echo.
echo  === DSH 会话重压 安装 ===
echo 脚本目录: %SCRIPT_DIR%

where python >nul 2>&1
if errorlevel 1 (
  echo  [!] 找不到 python，请先安装 Python 3.9+ 并加进 PATH
  pause
  exit /b 1
)

"%PY%" -c "import zstandard" 2>nul
if errorlevel 1 (
  echo  [*] 安装依赖 zstandard ...
  "%PY%" -m pip install zstandard
)

set DSH_EXE=
for %%P in ("%LOCALAPPDATA%\Programs\DeepSeek Harness\DeepSeek Harness.exe" "%PROGRAMFILES%\DeepSeek Harness\DeepSeek Harness.exe") do (
  if exist %%P set DSH_EXE=%%~P
)
if "%DSH_EXE%"=="" (
  echo  [!] 没自动找到 DeepSeek Harness.exe
  set /p DSH_EXE=  请粘贴完整路径（可留空，留空则用 dsh web 启动）: 
)

echo.
echo  [*] 创建计划任务 DshSessionRepack（每天 04:00）...
schtasks /Create /TN "DshSessionRepack" /SC DAILY /ST 04:00 /RL HIGHEST /F ^
  /TR "\"%PY%\" \"%SCRIPT_DIR%repack.py\" --restart --threshold-mb %THRESHOLD% --exe \"%DSH_EXE%\""

echo.
echo  完成。可以现在跑一次试试：
echo    "%PY%" "%SCRIPT_DIR%repack.py" --dry
echo  卸载：
echo    schtasks /Delete /TN "DshSessionRepack" /F
echo.
pause
