@echo off
setlocal EnableExtensions

set "PROJECT=C:\scripts\YoutubeMusicAPI"
set "PYTHON=%PROJECT%\.venv\Scripts\python.exe"
set "SCRIPT=%PROJECT%\ytm_like.py"

if not exist "%SCRIPT%" (
  echo ERROR: Script not found: %SCRIPT% 1>&2
  exit /b 2
)

if exist "%PYTHON%" goto :run

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found. Create %PROJECT%\.venv first. 1>&2
  exit /b 2
)
set "PYTHON=py -3"

:run
%PYTHON% "%SCRIPT%" like-current
exit /b %errorlevel%
