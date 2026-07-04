@echo off
rem Porneste trackerul in fundal (fara fereastra de consola).
cd /d "%~dp0"
start "" /min pythonw selly_tracker.py track
if errorlevel 1 (
    echo Nu am gasit pythonw. Incerc cu python...
    start "" /min python selly_tracker.py track
)
echo Trackerul a fost pornit in fundal.
timeout /t 3 >nul
