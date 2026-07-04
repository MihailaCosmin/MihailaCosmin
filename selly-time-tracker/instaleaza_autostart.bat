@echo off
rem Seteaza trackerul sa porneasca automat la fiecare logare in Windows.
cd /d "%~dp0"
schtasks /Create /F /TN "SellyTimeTracker" /SC ONLOGON /TR "pythonw.exe \"%~dp0selly_tracker.py\" track"
if errorlevel 1 (
    echo Nu am putut crea task-ul. Ruleaza acest fisier ca Administrator.
) else (
    echo Gata! Trackerul va porni automat la fiecare logare in Windows.
    echo Pentru a-l porni si acum, ruleaza porneste_tracker.bat
)
pause
