@echo off
cd /d "%~dp0"
echo Starting Islamweb QA v3...
echo.
echo Open browser: http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo Health:       http://localhost:8000/health
echo.
call env\Scripts\activate.bat
python main.py
pause
