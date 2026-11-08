@echo off
rem This Source Code Form is subject to the terms of the Mozilla Public
rem License, v. 2.0. If a copy of the MPL was not distributed with this
rem file, You can obtain one at https://mozilla.org/MPL/2.0/.
rem
rem Copyright (c) 2026 Creaddinscart Teams & CC Team
rem SPDX-License-Identifier: MPL-2.0
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py"
if "%PY%"=="" where python >nul 2>nul && set "PY=python"
if "%PY%"=="" (
  echo Python 3 not found. Install it from https://www.python.org/downloads/
  echo Make sure to check "Add Python to PATH", then run: python -m pip install windows-curses
  pause
  exit /b 1
)
%PY% launch.py
pause
