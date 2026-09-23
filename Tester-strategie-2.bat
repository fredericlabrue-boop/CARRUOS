@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CARRUOS - strategie 2
set PY=
where py >nul 2>&1 && set PY=py
if "%PY%"=="" where python >nul 2>&1 && set PY=python
if "%PY%"=="" (
  echo. & echo   Python introuvable. Installez-le depuis python.org
  echo   en cochant "Add python.exe to PATH".
  echo. & pause & exit /b 1
)
echo.
echo   STRATEGIE 2 - DERIVE POST-ANNONCE
echo.
echo   1. La preparation : dates d'annonces, cours, repetition generale
echo      sur la periode de conception. Repetable a volonte.
echo   2. Le passage UNIQUE sur 2024-2026 : il ne part que si vous tapez
echo      OUI, et son resultat s'inscrit au registre quel qu'il soit.
echo.
echo   Comptez 10 a 30 minutes la premiere fois.
echo.
%PY% -m equity_scanner.pead
echo.
pause
