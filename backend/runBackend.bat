@echo off
setlocal

REM Always run from this script directory (backend)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] Khong tim thay venv: .venv\Scripts\activate.bat
  echo Tao venv truoc:
  echo   py -3.12 -m venv .venv
  pause
  exit /b 1
)

if not exist "app.py" (
  echo [ERROR] Khong tim thay app.py. Hay dat file nay trong thu muc backend.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [WARNING] Chua co file .env trong backend. API co the loi khi chay.
)

set "BACKEND_DIR=%cd%"
set "VENV_ACTIVATE=%BACKEND_DIR%\.venv\Scripts\activate.bat"

echo Open 2 termials...
echo 1) Backend API  : python app.py
echo 2) Backend ML   : python -m ml.forecast_server
echo.

start "Backend API" cmd /k "cd /d ""%BACKEND_DIR%"" && call ""%VENV_ACTIVATE%"" && python app.py"
start "Backend ML" cmd /k "cd /d ""%BACKEND_DIR%"" && call ""%VENV_ACTIVATE%"" && python -m ml.forecast_server"

echo Done

endlocal
exit /b 0
