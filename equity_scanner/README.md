# equity_scanner — scanner actions « Repli en tendance » v1.0

Génère une liste de candidats quotidiens à partir des 4 blocs du système, avec
niveau d'entrée, stop et taille de position. Conçu pour être posé à côté
d'Alfred dans le même repo.

## Installation

```bash
pip install pandas numpy yfinance lxml     # source yf (défaut)
pip install ib_insync                       # source ibkr (optionnel)
```

## Vérifier avant d'utiliser

```bash
python -m equity_scanner.test_rules
```

21 tests sur données synthétiques : indicateurs, les 13 blocs, les vetos, le
dimensionnement. Chaque cas négatif vérifie que le rejet vient du **bon** bloc,
pas seulement que le signal ne part pas.

## Utilisation

```bash
# quelques titres
python -m equity_scanner.scan --tickers AMD,AVGO,MU,LRCX --sleeve 8000

# univers complet (compter ~15 min avec yfinance)
python -m equity_scanner.scan --universe sp500 --sleeve 8000 --pause 0.3 \
    --open NBIS --csv candidats.csv --verbose

# via TWS (API à activer : Global Config → API → Enable Socket Clients)
python -m equity_scanner.scan --tickers AMD,MU --sleeve 8000 --source ibkr
```

À lancer **après la clôture US** (22h/23h Paris). Toutes les règles sont
évaluées sur clôture ; un scan en séance produit des signaux qui n'existeront
pas à 22h.

## Ce que sort le scanner

D'abord le régime marché. Si SPY est sous sa SMA200, le scan **s'arrête** : pas
d'entrée, et la règle de sortie 5 impose la liquidation du sleeve sous 3
séances.

Sinon, les 5 meilleurs candidats classés par force relative 6 mois, avec entrée,
stop, risque unitaire, nombre de titres et risque en euros. S'il n'y a aucun
candidat — le cas le plus fréquent — il affiche les 5 titres les plus proches et
le bloc qui manque à chacun. C'est cette liste-là qui t'apprend le plus.

## Correction de conception trouvée au test

La spec v1.0 exigeait `histogramme MACD > 0` comme déclencheur. Le test l'a
invalidée : un repli pousse l'histogramme en négatif **par construction**, et
attendre son retour au-dessus de zéro fait entrer 4 à 6 séances après le point
bas, souvent 3 % plus haut.

Corrigé ainsi :
- La **ligne** MACD > 0 devient une condition de **régime** (bloc 1e). Elle reste
  positive pendant un repli sain — c'est ce qui distingue un repli d'un
  retournement.
- Le **déclencheur** (bloc 3a) est le retournement de l'histogramme
  (`hist > hist veille`), pas son passage au-dessus de zéro.

## Limites connues

- `data.py` n'a pas pu être testé (pas d'accès aux fournisseurs de données dans
  l'environnement où ce code a été écrit). Teste-le sur 2-3 titres d'abord.
- `sp500_tickers()` lit la composition **actuelle** depuis Wikipédia. Pour un
  backtest, fige un CSV daté, sinon tu introduis un biais du survivant qui
  gonflera mécaniquement ton profit factor.
- Le classement par force relative 6 mois est un **départage**, pas un signal
  validé. Il ajoute un degré de liberté et doit passer la Phase 0 comme le reste.
- Le veto résultats dépend de yfinance, peu fiable. `None` = inconnu → veto
  explicite. Ne le désactive pas.

## Statut

Le scanner est un **générateur de candidats**. Tant que la Phase 0 n'a pas rendu
un GO (≥ 200 trades OOS, PF ≥ 1,15, z ≥ 2, drawdown < 20 %), sa sortie est une
watchlist, pas une liste d'ordres.
