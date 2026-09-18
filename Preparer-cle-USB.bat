@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CARRUOS - preparer une cle USB

echo.
echo   PREPARER UNE CLE USB
echo   ====================
echo.
echo   Copie Carruos sur une cle, avec ses dependances embarquees dans
echo   un dossier lib. Sur un poste ou pandas n'est pas installe, le
echo   paquet ira les chercher la  (voir equity_scanner\__init__.py).
echo.
echo   Il faut quand meme Python sur le poste d'accueil : seules les
echo   bibliotheques voyagent, pas l'interpreteur.
echo.

set PY=
where py >nul 2>&1 && set PY=py
if "%PY%"=="" where python >nul 2>&1 && set PY=python
if "%PY%"=="" (
  echo   Python introuvable sur CE poste.
  echo. & pause & exit /b 1
)

set DEST=
set /p DEST=   Lettre ou chemin de la cle (exemple E:\CARRUOS) :
if "%DEST%"=="" exit /b 0

echo.
echo   Copie des fichiers vers "%DEST%"...
robocopy "." "%DEST%" /E /NFL /NDL /NJH /NJS ^
  /XD .git __pycache__ .bruce_cache lib ^
  /XF *.pyc *.csv dashboard.html
if errorlevel 8 (
  echo   La copie a echoue. Verifie que la cle est accessible en ecriture.
  echo. & pause & exit /b 1
)

echo.
echo   Telechargement des dependances dans "%DEST%\lib"...
echo   (compter quelques minutes la premiere fois)
%PY% -m pip install --upgrade --target "%DEST%\lib" ^
  pandas numpy yfinance lxml pywebview
if errorlevel 1 (
  echo.
  echo   Le telechargement a echoue. La cle contient quand meme le code :
  echo   sur le poste d'accueil, lance Carruos.bat et choisis 2.
)

echo.
echo   Termine. Sur l'autre poste : ouvrir "%DEST%" et lancer Carruos.bat.
echo.
pause
