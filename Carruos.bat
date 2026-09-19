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
  echo   Carruos.bat doit etre a cote du dossier equity_scanner.
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
echo      5.  PHASE 0 - go/no-go sur le S^&P 500
echo      6.  PHASE 0 - test rapide sur 120 titres US
echo      P.  Derive post-annonce - univers US large
echo      S.  Derive post-annonce NEGATIVE - vente a decouvert
echo.
echo      --- DONNEES ET CONTROLES ---
echo      Q.  Pourquoi un titre est-il refuse ?
echo      J.  Journal d'audit des signaux
echo      F.  Figer la composition d'un univers  (chaque trimestre)
echo      C.  Etat du cache des cours
echo      R.  Epreuves de robustesse sur un rapport CSV
echo      Z.  Calibrer le critere 4 sur des cours aleatoires
echo      H.  Amplitude par horizon et take-profit envisageable
echo      O.  Horaires des places europeennes et americaines
echo.
echo      --- COMPTE IBKR (lecture seule) ---
echo      7.  Portefeuille - TWS papier        (7497)
echo      8.  Portefeuille - IB Gateway papier (4002)
echo      G.  Portefeuille - compte REEL
echo.
echo      9.  Tests du systeme  (les trois)
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
if /i "%CHOIX%"=="S" goto short
if /i "%CHOIX%"=="Q" goto qualite
if /i "%CHOIX%"=="J" goto audit
if /i "%CHOIX%"=="F" goto figer
if /i "%CHOIX%"=="C" goto cachetat
if /i "%CHOIX%"=="R" goto robuste
if /i "%CHOIX%"=="Z" goto calib
if /i "%CHOIX%"=="H" goto horizon
if /i "%CHOIX%"=="O" goto places
if "%CHOIX%"=="9" goto tests
if "%CHOIX%"=="0" exit /b 0
goto menu

:run
echo   Ouverture de la fenetre Carruos...
%PY% -m equity_scanner.app
echo. & pause & goto menu

:install
%PY% -m pip install --upgrade pandas numpy yfinance lxml pywebview
echo.
echo   ib_insync n'est utile que pour le module portefeuille (compte IBKR).
set IB=
set /p IB=   L'installer aussi ? (o/N) :
if /i "%IB%"=="o" %PY% -m pip install --upgrade ib_insync
echo.
echo   pywebview installe = vraie fenetre Windows.
echo   Sans lui, Carruos s'ouvre dans le navigateur.
echo. & pause & goto menu

:raccourci
if not exist "Creer-raccourci.vbs" (
  echo   Creer-raccourci.vbs introuvable a cote de ce fichier.
  echo. & pause & goto menu
)
cscript //nologo "Creer-raccourci.vbs"
echo. & pause & goto menu

:usb
if not exist "Preparer-cle-USB.bat" (
  echo   Preparer-cle-USB.bat introuvable a cote de ce fichier.
  echo. & pause & goto menu
)
call "Preparer-cle-USB.bat"
goto menu

:ph0
echo   Phase 0 sur le S^&P 500.
echo   Premiere passe : telechargement de 500 titres sur 20 ans.
echo   Les passes suivantes relisent le cache et sont bien plus rapides.
echo.
%PY% -m equity_scanner.phase0 --univers sp500 --csv "phase0-sp500.csv"
echo. & pause & goto menu

:ph0rapide
%PY% -m equity_scanner.phase0 --univers us --csv "phase0-us.csv"
echo. & pause & goto menu

:pead
echo.
echo   Derive post-annonce - regles GELEES, un seul passage.
echo   Collecte des dates d'annonces puis rejeu.
echo.
%PY% -m equity_scanner.pead --univers us --csv "pead-us.csv"
echo. & pause & goto menu

:short
echo.
echo   VENTE A DECOUVERT - regles GELEES, un seul passage.
echo.
echo   Ce n'est pas la strategie a l'achat avec les signes inverses.
echo   La perte n'est pas bornee, la position grossit quand elle a tort,
echo   et emprunter les titres se paie. Le dividende du au preteur n'est
echo   PAS modelise : retranche 0,4 point par trade au resultat affiche.
echo.
%PY% -m equity_scanner.short --univers us --csv "short-us.csv"
echo. & pause & goto menu

:qualite
echo   Controle qualite d'un ou plusieurs titres.
echo   Exemple : AAPL MC.PA NESN.SW
set TK=
set /p TK=   Tickers separes par un espace :
if "%TK%"=="" goto menu
%PY% -m equity_scanner.qualite %TK%
echo. & pause & goto menu

:audit
%PY% -m equity_scanner.audit
echo.
echo   --- parametres geles et leur empreinte ---
%PY% -m equity_scanner.audit --verifie
echo. & pause & goto menu

:figer
echo   Enregistre la composition DU JOUR d'un univers, datee.
echo   A faire chaque trimestre : c'est ce qui construit l'historique
echo   qui manque pour corriger le biais du survivant.
echo.
set UNI=
set /p UNI=   Univers (sp500, nasdaq100, us, cac40, dax, europe...) :
if "%UNI%"=="" goto menu
%PY% -m equity_scanner.data --figer %UNI%
echo. & pause & goto menu

:cachetat
%PY% -m equity_scanner.cache --etat
echo.
set PU=
set /p PU=   Purger les series de plus de 30 jours ? (o/N) :
if /i "%PU%"=="o" %PY% -m equity_scanner.cache --purge 30
echo. & pause & goto menu

:robuste
echo   Stabilite, Monte Carlo et bootstrap sur un rapport deja calcule.
echo.
dir /b *.csv 2>nul
echo.
set RC=
set /p RC=   Nom du fichier CSV :
if "%RC%"=="" goto menu
%PY% -m equity_scanner.robuste --csv "%RC%"
echo. & pause & goto menu

:calib
echo.
echo   Le critere 4 est, dit le protocole, le seul qui compte vraiment.
echo   Ceci le met a l'epreuve sur des cours PUREMENT ALEATOIRES, ou il
echo   n'y a rien a trouver. Un temoin honnete doit rendre un z centre
echo   sur zero. Compte plusieurs minutes.
echo.
set NU=
set /p NU=   Combien d'univers ? (12 par defaut) :
if "%NU%"=="" set NU=12
%PY% -m equity_scanner.calibration --univers %NU%
echo. & pause & goto menu

:horizon
echo.
echo   Ce que le titre bouge a chaque horizon - 1 jour, 1 semaine, 1 mois,
echo   3 mois, 6 mois, 1 an - et quel objectif de prise de profit il a
echo   reellement atteint dans le passe, en combien de seances, et
echo   combien de fois il a tout rendu ensuite.
echo.
echo   AUCUNE DIRECTION. C'est une propriete du titre, pas un signal.
echo.
set HT=
set /p HT=   Ticker (NVDA, MC.PA, TLX...) :
if "%HT%"=="" goto menu
%PY% -m equity_scanner.horizon %HT%
echo. & pause & goto menu

:places
echo.
echo   Les neuf places, en heure de Paris, heure d'ete comprise.
echo   Plus ce que le programme peut et ne peut PAS dire sur l'heure
echo   a laquelle passer un ordre.
echo.
%PY% -m equity_scanner.seance
echo. & pause & goto menu

:pfpapier
echo   TWS ou IB Gateway doit etre lance, API activee.
echo.
%PY% -m equity_scanner.portefeuille
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

:tests
echo   Les trois tests doivent passer. Aucun ne touche au reseau.
echo.
%PY% -m equity_scanner.test_rules
echo.
%PY% -m equity_scanner.test_moteur
echo.
%PY% -m equity_scanner.test_pages
echo. & pause & goto menu
