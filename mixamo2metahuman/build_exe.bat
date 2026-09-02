@echo off
REM Construieste Mixamo2MetaHuman.exe si pune tot ce trebuie intr-un folder.
REM   build_exe.bat                 -> foldere in dist\Mixamo2MetaHuman
REM   build_exe.bat D:\Proiecte     -> si il copiaza pe D:\Proiecte
setlocal
cd /d "%~dp0"

set DEST=%~1

echo === Caut Python ===
set PY=
where py >nul 2>&1 && set PY=py -3
if "%PY%"=="" (where python >nul 2>&1 && set PY=python)
if "%PY%"=="" (
  echo Nu am gasit Python. Instaleaza-l de pe python.org ^(bifeaza "Add to PATH"^).
  pause
  exit /b 1
)

echo === Pregatesc mediul de build ===
if not exist "build\_venv" %PY% -m venv "build\_venv" || goto :eroare
call "build\_venv\Scripts\activate.bat" || goto :eroare
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller || goto :eroare

echo === Verific aplicatia ===
python -m unittest discover -s tests || goto :eroare

echo === Construiesc executabilul ===
if "%DEST%"=="" (
  python build\package.py || goto :eroare
) else (
  python build\package.py --dest "%DEST%" || goto :eroare
)

echo.
echo Gata. Executabilul e Mixamo2MetaHuman.exe din folderul de mai sus.
pause
exit /b 0

:eroare
echo.
echo Build esuat. Mesajul de eroare e mai sus.
pause
exit /b 1
