@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m bridge.server %*
if errorlevel 1 goto fail
exit /b 0
:fail
 echo Startup failed. Check Python 3.10+ and the error above.
 pause
 exit /b 1
