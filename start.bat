@echo off
REM One-click setup and start for Windows: double-click this file, or run start.bat
cd /d "%~dp0"

if not exist .venv (
  echo Creating Python virtual environment...
  python -m venv .venv || goto :error
)
echo Installing Python packages...
call .venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt || goto :error

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo   Created .env  --  open it and paste your ANTHROPIC_API_KEY to enable AI questions.
  echo.
)

if not exist frontend\dist\index.html (
  echo Building the website...
  pushd frontend
  call npm install --no-audit --no-fund || goto :error
  call npm run build || goto :error
  popd
)

set OPEN_BROWSER=1
cd backend
..\.venv\Scripts\python.exe -m app
goto :eof

:error
echo.
echo Setup failed. See the messages above. You need Python 3.11+ and Node.js 20+ installed.
pause
