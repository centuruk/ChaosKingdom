@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv
    if errorlevel 1 goto :fail
)
.venv\Scripts\python.exe -c "import pygame" >nul 2>&1
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
)
.venv\Scripts\python.exe launch.py
if errorlevel 1 goto :fail
exit /b 0
:fail
echo Python 3.10 or newer is required. See README.md for installation instructions.
pause
exit /b 1
