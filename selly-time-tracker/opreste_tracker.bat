@echo off
rem Opreste trackerul folosind PID-ul salvat in tracker.pid.
cd /d "%~dp0"
if not exist tracker.pid (
    echo Trackerul nu pare sa ruleze (nu exista tracker.pid).
    pause
    exit /b
)
set /p PID=<tracker.pid
taskkill /PID %PID% /F >nul 2>&1
if errorlevel 1 (
    echo Nu am putut opri procesul %PID% - poate era deja oprit.
) else (
    echo Tracker oprit (PID %PID%).
)
del tracker.pid >nul 2>&1
pause
