@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title CARRUOS

set PY=
where py >nul 2>&1 && set PY=py
if "%PY%"=="" where python >nul 2>&1 && set PY=python
if "%PY%"=="" (
  echo. & echo   Python introuvable. Installe-le depuis python.org
  echo   en cochant "Add python.exe to PATH".
  echo. & pause & exit /b 1
)
if not exist "equity_scanner\app.py" (
  echo. & echo   equity_scanner\app.py introuvable.
  echo   bruce.bat doit etre dans IBKR, a cote du dossier equity_scanner.
  echo. & pause & exit /b 1
)

:menu
cls
echo.
echo   ============================================
echo      C A R R U O S
echo      scanner actions - repli en tendance
echo   ============================================
echo.
echo      1.  Lancer Carruos
echo      2.  Installer / mettre a jour  (a faire une fois)
echo      3.  Creer le raccourci sur le Bureau
echo      4.  Preparer une cle USB
echo.
echo      --- VALIDATION ---
echo      5.  PHASE 0 - go/no-go sur le S&P 500  (5-10 min)
echo      6.  PHASE 0 - test rapide sur 120 titres US
echo.
echo.
echo      --- COMPTE IBKR (lecture seule) ---
echo      7.  Portefeuille - TWS papier        (7497)
echo      8.  Portefeuille - IB Gateway papier (4002)
echo      G.  Portefeuille - compte REEL
echo.
echo    ----  HYPOTHESE 2 : DERIVE POST-ANNONCE  -------------------
echo      P.  Lancer le test PEAD sur l'univers US large
echo.
echo      9.  Tests du systeme
echo      0.  Quitter
echo.
echo      Astuce : Carruos.vbs lance l'appli sans cette console.
echo.
set CHOIX=
set /p CHOIX=   Ton choix :
echo.
if "%CHOIX%"=="1" goto run
if "%CHOIX%"=="2" goto install
if "%CHOIX%"=="3" goto raccourci
if "%CHOIX%"=="4" goto usb
if "%CHOIX%"=="5" goto ph0
if "%CHOIX%"=="6" goto ph0rapide
if "%CHOIX%"=="7" goto pfpapier
if "%CHOIX%"=="8" goto pfgw
if /i "%CHOIX%"=="G" goto pfreel
if /i "%CHOIX%"=="P" goto pead
if "%CHOIX%"=="9" goto tests
if "%CHOIX%"=="0" exit /b 0
goto menu

:run
echo   Ouverture de la fenetre Carruos...
%PY% -m equity_scanner.app
echo. & pause & goto menu

:install
%PY% -m pip install --upgrade pandas numpy yfinance lxml pywebview ib_insync
echo.
echo   pywebview installe = vraie fenetre Windows.
echo   Sans lui, Bruce s'ouvre dans le navigateur.
echo. & pause & goto menu

:raccourci
cscript //nologo "Creer-raccourci.vbs"
goto menu

:usb
call "Preparer-cle-USB.bat"
goto menu

:ph0
echo   Phase 0 sur le S&P 500. Compter 5 a 10 minutes.
echo.
%PY% -m equity_scanner.phase0 --univers sp500 --csv "phase0-sp500.csv"
echo. & pause & goto menu

:ph0rapide
%PY% -m equity_scanner.phase0 --univers us --csv "phase0-us.csv"
echo. & pause & goto menu

:pfpapier
echo   TWS ou IB Gateway doit etre lance, API activee.
echo.
%PY% -m equity_scanner.portefeuille
echo. & pause & goto menu

:pead
echo.
echo   Derive post-annonce - regles GELEES, un seul passage.
echo   Collecte des dates d'annonces puis rejeu. Compte 30-60 min.
echo.
%PY% -m equity_scanner.pead --univers us --csv "pead-us.csv"
echo. & pause & goto menu

:pfgw
echo   IB Gateway doit etre lance en mode Paper Trading, API activee.
echo.
%PY% -m equity_scanner.portefeuille --port 4002
echo. & pause & goto menu

:pfreel
echo   Compte REEL. Lecture seule, aucun ordre ne sera passe.
set RP=
set /p RP=   Port (7496 pour TWS, 4001 pour IB Gateway) :
if "%RP%"=="" goto menu
%PY% -m equity_scanner.portefeuille --port %RP%
echo. & pause & goto menu

:VIEUX_pfreel
echo   Compte REEL, en lecture seule. Aucun ordre ne sera passe.
echo.
%PY% -m equity_scanner.portefeuille --reel
echo. & pause & goto menu

:tests
%PY% -m equity_scanner.test_rules
echo.
%PY% -m equity_scanner.test_moteur
echo.
%PY% -m equity_scanner.test_pages
echo. & pause & goto menu
