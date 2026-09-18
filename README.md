# CARRUOS

Scanner d'actions personnel. Python, interface HTML servie en local et
affichée dans une fenêtre Windows.

---

## Installation, une seule fois

1. **Python 3.11 ou plus**, depuis [python.org](https://www.python.org/downloads/).
   Cocher **« Add python.exe to PATH »** pendant l'installation — sans
   cette case, rien ne démarrera.
2. Décompresser cette archive où vous voulez (Documents, un disque
   externe, peu importe).
3. Double-cliquer **`Carruos.bat`**, choisir **2. Installer**.
4. Choisir **9. Tests du système**. Les trois doivent passer.
5. Choisir **1. Lancer Carruos**.

`3. Créer le raccourci` pose un lanceur sur le Bureau.
`4. Préparer une clé USB` emporte le tout, dépendances comprises.

---

## Le menu

| | |
|---|---|
| **1** | lancer l'application |
| **2** | installer ou mettre à jour les dépendances |
| **5 / 6** | Phase 0 — go/no-go, S&P 500 ou 120 titres US |
| **P** | dérive post-annonce (hypothèse 2) |
| **Q** | pourquoi un titre est-il refusé ? |
| **J** | journal d'audit des signaux |
| **F** | figer la composition d'un univers |
| **C** | état du cache des cours |
| **R** | épreuves de robustesse sur un rapport déjà calculé |
| **7 / 8 / G** | portefeuille IBKR, **lecture seule** |
| **9** | les trois tests |

---

## À faire chaque trimestre : `F`

Le backtest teste le passé avec la composition **d'aujourd'hui** du
S&P 500. C'est le biais du survivant : les faillites et les retraits de
cote ont été retirés de l'échantillon après coup, donc le backtest ne
peut pas perdre dessus et son résultat est flatté.

Personne ne peut remonter le temps. On peut arrêter d'en perdre :
`F` enregistre la composition du jour, datée. Dans trois ans, ces
fichiers seront l'historique qui manque aujourd'hui. Tant qu'aucune
composition d'époque ne couvre la période testée, la Phase 0 écrit
l'avertissement en tête de son rapport.

---

## Ce qui est mesuré, ce qui ne l'est pas

Le programme refuse par construction d'afficher :

- un pourcentage unique de « chances de gagner » — toujours l'intervalle
  de Wilson **avec** le nombre de trades ;
- un score composite bâti sur des poids non testés ;
- un verdict directionnel (HAUSSIER, ACHAT) dérivé d'un tel score ;
- une ligne de prédiction de prix. Le cône de dispersion a sa dérive
  fixée à zéro : il donne l'amplitude, jamais le sens.

**Les paramètres de stratégie sont gelés**, et la règle est exécutable :
`audit.empreinte()` calcule le SHA256 de toutes les constantes, et
`test_moteur` tombe si l'une d'elles bouge. Un résultat ne peut plus
être attribué par erreur à un jeu de paramètres qui ne l'a pas produit.

**État de la validation.** Stratégie 1, « repli en tendance » : **NO-GO**.
L'hypothèse est morte et ne se retouche pas. Stratégie 2, dérive
post-annonce : moteur codé, test pas encore lancé.

---

## Quand un titre disparaît d'un scan

Il ressort toujours avec son motif : série trouée, division non ajustée,
cotation figée, volume nul, données périmées, décrochage du calendrier
de l'indice. Le principe est de **refuser de conclure** plutôt que de
compléter une barre manquante en silence — une barre inventée fausse le
RVOL, l'ATR et le RSI de la séance, et le signal qui en sort a l'air
parfaitement normal.

Pour savoir précisément ce qui bloque : menu **Q**, ou

```
py -m equity_scanner.qualite AAPL MC.PA
```

---

## Si quelque chose ne va pas

| Symptôme | Cause la plus fréquente |
|---|---|
| « Python introuvable » | case *Add python.exe to PATH* oubliée ; réinstaller |
| l'appli s'ouvre dans le navigateur | `pywebview` absent ; menu **2** |
| un scan ne rend aucun candidat | marché sous sa MM200 : c'est la règle, pas une panne |
| tous les titres sont refusés | menu **Q** sur l'un d'eux : le motif est écrit |
| un scan semble lent la première fois | premier passage = téléchargement ; les suivants relisent le cache |
| `test_moteur` échoue sur l'empreinte | un paramètre gelé a bougé. Ce n'est pas le test qu'il faut corriger |

Le cache des cours, la clé Alpha Vantage, les positions et le journal
d'audit vivent dans `.bruce_cache`, à côté du programme. Supprimer ce
dossier remet tout à zéro sans rien casser.

---

## Pour les curieux : la ligne de commande

```
py -m equity_scanner.app                       l'application
py -m equity_scanner.scan --tickers AMD,MU --sleeve 8000
py -m equity_scanner.phase0 --univers sp500 --csv rapport.csv
py -m equity_scanner.qualite AAPL              contrôle qualité
py -m equity_scanner.audit --parametres        paramètres gelés + empreinte
py -m equity_scanner.robuste --csv rapport.csv stabilité, Monte Carlo
py -m equity_scanner.cache --etat              taille du cache
py -m equity_scanner.data --figer sp500        composition datée
```

`--fils N` règle le nombre de téléchargements simultanés (8 par défaut,
16 au maximum : au-delà, Yahoo limite le débit).

À lancer **après la clôture US** (22h ou 23h heure de Paris). Toutes les
règles sont évaluées sur clôture ; un scan en séance produit des signaux
qui n'existeront plus le soir.
