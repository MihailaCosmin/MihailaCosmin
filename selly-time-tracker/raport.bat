@echo off
rem Afiseaza raportul pe saptamana curenta.
cd /d "%~dp0"
python selly_tracker.py report saptamana
echo.
pause
