# CARRUOS — contexte pour Claude Code

Scanner d'actions personnel de Frédéric. Python, interface HTML servie en
local et affichée dans une fenêtre pywebview.

## Lancer

```
py -m equity_scanner.app          # l'application
py -m equity_scanner.test_pages   # contrôle des pages générées
py -m equity_scanner.test_rules   # contrôle des règles
```

**Les deux tests doivent passer avant tout commit.**

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

## Ce qu'il ne faut jamais afficher

- Un pourcentage unique de « chances de gagner ». Toujours l'intervalle
  de confiance de Wilson avec le nombre de trades.
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
| `data.py` | chargement yfinance, 8 univers |
| `reglages.py` | 13 effets visuels débrayables |

## Chantiers ouverts, par priorité

1. **Univers historiques** — le backtest utilise la composition
   *actuelle* du S&P 500 pour tester le passé. Biais du survivant.
2. **Contrôle qualité des données** — bloquant : barres manquantes,
   gaps anormaux, désynchronisation avec l'indice. Refuser de produire
   un signal plutôt que de compléter silencieusement.
3. **Journal d'audit** — identifiant unique par signal, horodatage,
   valeurs des indicateurs, version de stratégie.
4. **Walk-forward et Monte Carlo** sur l'ordre des trades.
5. **Corporate actions** au-delà des splits : changements de ticker,
   fusions, retraits de cote.

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
