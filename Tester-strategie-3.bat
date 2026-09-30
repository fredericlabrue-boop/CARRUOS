@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CARRUOS - strategie 3
set PY=
where py >nul 2>&1 && set PY=py
if "%PY%"=="" where python >nul 2>&1 && set PY=python
if "%PY%"=="" (
  echo. & echo   Python introuvable. Installez-le depuis python.org
  echo   en cochant "Add python.exe to PATH".
  echo. & pause & exit /b 1
)
echo.
echo   STRATEGIE 3 - DERIVE POST-ANNONCE NEGATIVE, VENTE A DECOUVERT
echo.
echo   Le dividende du au preteur n'est PAS modelise : le resultat est
echo   optimiste d'environ 0,3 a 0,4 point par trade.
echo.
echo   1. Valider les deux documents, une fois : la note de lecture
echo      strategie-short-v1-lecture.md et l'amendement n.1
echo      strategie-short-v1-amendement-1.md. Lisez-les d'abord.
echo   2. La preparation, puis le passage UNIQUE sur 2024-2026 : il ne
echo      part que si les documents sont valides et que vous tapez OUI -
echo      ou LANCER QUAND MEME si la repetition a rendu NO-GO.
echo   3. La preparation seule, repetable a volonte.
echo   0. Quitter
echo.
set CHOIX=
set /p CHOIX=   Votre choix :
echo.
if "%CHOIX%"=="1" goto documents
if "%CHOIX%"=="2" goto passage
if "%CHOIX%"=="3" goto preparation
exit /b 0

:documents
%PY% -m equity_scanner.short --valider-documents
goto fin

:passage
echo   Comptez 15 a 40 minutes la premiere fois.
%PY% -m equity_scanner.short
goto fin

:preparation
%PY% -m equity_scanner.short --preparer

:fin
echo.
pause
