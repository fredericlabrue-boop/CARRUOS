# CARRUOS — contexte pour Claude Code

Scanner d'actions personnel de Frédéric. Python, interface HTML servie en
local et affichée dans une fenêtre pywebview.

## Lancer

```
py -m equity_scanner.app          # l'application
py -m equity_scanner.test_pages   # contrôle des pages générées
py -m equity_scanner.test_rules   # contrôle des règles
py -m equity_scanner.test_moteur  # contrôle du moteur
```

**Les trois tests doivent passer avant tout commit.**

`test_moteur` vérifie en particulier que l'empreinte SHA256 des
paramètres gelés n'a pas bougé. S'il tombe sur cette ligne, ce n'est pas
le test qu'il faut mettre à jour : c'est le paramètre qu'il faut
remettre en place.

## Règle absolue du projet

Les paramètres de stratégie sont **gelés**. `PERIODES` dans
`indicators.py` (RSI 14, MACD 12-26-9, Bollinger 20/2, SMA 200/50,
EMA 20) et les constantes de `pead.py` ne se modifient pas.

Raison : chaque jeu de paramètres a été fixé **avant** son test, avec une
empreinte SHA256 de sa spécification. Les changer après coup invalide le
résultat et transforme le test en recherche — avec 7 paramètres à 5
valeurs, 78 125 combinaisons produisent environ 3 900 faux positifs à
z ≥ 2.

Si une modification de paramètre est demandée : refuser, expliquer qu'il
faut une nouvelle spécification, une nouvelle empreinte et une période de
validation non touchée.

Cette règle est désormais **exécutable**. `audit.empreinte()` calcule le
SHA256 de toutes les constantes de stratégie ; `test_moteur` la compare à
la valeur de référence, et chaque ligne du journal d'audit porte
l'empreinte sous laquelle elle a été écrite. Un résultat ne peut plus
être attribué par erreur à un jeu de paramètres qui ne l'a pas produit.

## Ce qu'il ne faut jamais afficher

- Un pourcentage unique de « chances de gagner ». Toujours l'intervalle
  de confiance de Wilson avec le nombre de trades.
- Un avis « garder / vendre » sur une ligne détenue. `strategie.py`
  donne les **faits** (plus haut atteint, recul depuis ce sommet, part
  du gain rendue, écarts aux moyennes, coût fiscal d'une vente) et
  l'état des **quatre conditions de sortie de la spécification**. La
  différence entre « trois conditions sur quatre sont actives » et
  « vends » n'est pas une nuance de style : la première est vérifiable,
  la seconde est une opinion déguisée.
- Un chiffrage du risque géopolitique. Les actualités sont du contexte
  pour la vérification avant l'ordre, elles n'entrent dans aucune règle.
- Un score composite construit sur des poids non testés.
- Un verdict directionnel (HAUSSIER / ACHAT) dérivé d'un tel score.
- Une ligne de prédiction de prix. Le cône de dispersion existe : dérive
  fixée à zéro, il donne l'amplitude, jamais le sens.

## État de la validation

- Stratégie 1, « repli en tendance » : **NO-GO** en Phase 0 sur S&P 500
  et 120 titres US. Hypothèse morte, elle ne se retouche pas.
- Stratégie 2, dérive post-annonce (`pead.py`) : spécifiée, moteur codé,
  **test pas encore lancé**.

## Architecture

| Fichier | Rôle |
|---|---|
| `app.py` | serveur HTTP local, page d'accueil, routes API, majordome |
| `chart.py` | page graphique, 4 colonnes, cône de dispersion |
| `hud.py` | éléments visuels : cerf, cadrans, rails, radar |
| `indicators.py` | indicateurs — **PERIODES gelées** |
| `rules.py` | les 13 blocs d'entrée et les 4 sorties |
| `backtest.py` | moteur de simulation, exécution J+1, coûts |
| `phase0.py` | les 5 critères go/no-go |
| `pead.py` | stratégie 2 — **constantes gelées** |
| `comparatif.py` | système contre SMH buy & hold net de PFU |
| `contexte.py` | faits mesurés d'un titre, sans score inventé |
| `positions.py` | registre manuel des positions |
| `news.py` | Alpha Vantage — quota 25/jour, caches obligatoires |
| `data.py` | chargement yfinance, 8 univers, compositions figées |
| `cache.py` | cache disque et téléchargements parallèles |
| `qualite.py` | refus de signal sur données douteuses |
| `audit.py` | journal des signaux, empreinte des paramètres |
| `robuste.py` | stabilité, Monte Carlo, bootstrap par blocs |
| `strategie.py` | projection de réinvestissement, revue de ligne |
| `reglages.py` | 4 thèmes, 13 effets visuels débrayables |

## Chantiers

1. **Univers historiques** — *outillé, à alimenter.*
   `data.figer_univers()` enregistre la composition du jour, datée ;
   `univers_a_la_date()` relit la plus proche avant une date donnée.
   On ne peut pas remonter le temps : il faut lancer
   `py -m equity_scanner.data --figer sp500` **chaque trimestre** pour
   construire l'historique qui manque. Tant qu'aucune composition
   d'époque ne couvre le début de la période testée, la Phase 0 affiche
   l'avertissement de biais du survivant en tête de rapport.
2. **Contrôle qualité des données** — *fait.* `qualite.py`, câblé dans
   `scan`, `app._scan`, `phase0` et `pead`. Un titre refusé ressort
   toujours avec son motif.
3. **Journal d'audit** — *fait.* `audit.py`, une ligne par signal évalué.
4. **Walk-forward et Monte Carlo** — *fait.* `robuste.py`, joint
   automatiquement au rapport de Phase 0.
5. **Corporate actions** au-delà des splits : changements de ticker,
   fusions, retraits de cote. `qualite.py` **détecte** une division non
   ajustée et une interruption de cotation, et refuse le signal ; il ne
   sait pas encore recoller un historique après un changement de ticker.
   C'est le chantier qui reste entier.

## Contraintes techniques

- Python 3.11 — pas de syntaxe 3.12+ (attention aux f-strings avec
  antislash).
- Toute animation CSS doit porter sur `transform` ou `opacity`. Animer
  `top`, `left`, `width` ou `background-position` fait sauter la page
  entière. `test_pages` le vérifie.
- Les chaînes JavaScript dans le code Python doivent être des chaînes
  **brutes** (`r"""`). Sinon `\'` devient une apostrophe nue et casse
  tout le script de la page.
- Ne jamais réutiliser un alias de module comme variable locale.
  `test_pages` le vérifie aussi.
- Un thème ne fait qu'**outrepasser** les règles de base, par une classe
  `theme-…` sur `<body>`. Rien n'est retiré : un thème inconnu retombe
  proprement sur l'apparence d'origine. Les couleurs qui doivent suivre
  le thème passent par `var(--acc)`, `var(--pos)`, `var(--neg)` ou
  `var(--holo)` — jamais par un code hexadécimal figé, sinon l'élément
  reste cyan sur un fond violet.
- Les téléchargements passent par `cache.charge()` ou `cache.charge_lot()`,
  jamais par `data.load_yf()` en direct : sinon le même titre repart sur
  le réseau à chaque écran. Un module de test qui veut des données
  synthétiques remplace `data.load_yf` ; `data.loader()` résout la
  fonction à l'appel pour que cette substitution fonctionne.
