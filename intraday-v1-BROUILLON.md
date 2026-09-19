# SCALP ET DAY TRADING — ÉTAT DES LIEUX AVANT SPÉCIFICATION
### Rédigé le 19 septembre 2026, à la demande de Frédéric
### **Ceci n'est PAS une spécification. C'est ce qu'il faut régler avant d'en écrire une.**

---

## Pourquoi ce document n'est pas `intraday-v1.md`

Une spécification gèle des règles et reçoit une empreinte SHA256. Elle ne
se rédige qu'une fois qu'on sait **sur quelles données** elle sera testée,
parce que les données décident des règles — pas l'inverse.

Or, aujourd'hui, les données n'existent pas dans le programme. Écrire des
seuils maintenant reviendrait à les inventer, puis à les ajuster quand les
vraies données arriveraient. C'est exactement ce que le protocole
interdit.

Ce document liste donc les décisions à prendre. Quand elles seront
prises, `intraday-v1.md` pourra être écrit, gelé, et haché.

---

## ÉTAPE 0 — Le mur, et il est haut

### Ce que CARRUOS a aujourd'hui

`yfinance`, bougies **journalières**, 20 ans d'historique, gratuit.
L'ensemble du programme repose là-dessus : les 13 blocs d'entrée, les 4
sorties, la Phase 0, les trois empreintes.

### Ce que le scalp exige

| | scalp | day trading | swing (actuel) |
|---|---|---|---|
| Bougie | 1 s – 1 min | 1 – 15 min | 1 jour |
| Durée d'une position | secondes à minutes | heures | jours à semaines |
| Trades par an | des milliers | des centaines | des dizaines |
| Coût aller-retour | **décisif** | déterminant | supportable |
| Carnet d'ordres | indispensable | utile | inutile |

**La ligne « coût » est celle qui tue.** Sur le système actuel, entre
« clôture sans frais » et « ouverture J+1 + 0,15 % par côté », **92 % de
l'espérance disparaissait** — c'est mesuré, c'est dans le protocole. Un
scalpeur paie ce coût des dizaines de fois plus souvent.

Un aller-retour à 0,30 % répété 1 000 fois par an coûte **300 % du
capital engagé en frottements**. Une stratégie de scalp doit donc produire
un avantage brut supérieur à cela avant de gagner un centime.

---

## ÉTAPE 1 — Les trois questions du protocole, appliquées ici

Le protocole les exige avant toute règle. Elles n'ont pas encore de
réponse, et c'est le premier travail.

### 1. Quel comportement exploite-t-on ?

**Sans réponse pour l'instant.** « Le titre monte le matin » n'est pas un
comportement, c'est une observation. Les candidats sérieux sont :

- **déséquilibre du carnet d'ordres** — exige les données de carnet,
  que ni yfinance ni Alpha Vantage ne fournissent ;
- **retour à la moyenne après un écart d'ouverture** — testable avec des
  bougies 1 minute ;
- **continuation après la première demi-heure** — testable de même ;
- **réaction à une annonce** — c'est l'hypothèse 2 ou 3, à horizon plus
  court.

Seuls les deux du milieu sont atteignables avec des données achetables à
un prix raisonnable.

### 2. Qui est de l'autre côté, et pourquoi accepte-t-il de perdre ?

**C'est ici que ça devient difficile, et il faut le dire franchement.**

En journalier, les contreparties sont identifiables et contraintes : fonds
indiciels qui rééquilibrent à date fixe, mandats de style, vendeurs par
prise de profit. Aucun n'est mieux informé que vous.

En intraday, la contrepartie est un **teneur de marché automatisé**, qui
voit le carnet, qui a une latence de l'ordre de la microseconde, et dont
le métier est précisément de prendre l'autre côté de votre ordre en
gagnant le spread. Il n'est pas contraint : il est équipé.

> **À répondre avant d'écrire la spécification.** Si la réponse est
> « personne d'identifiable », le protocole dit de s'arrêter là. Ce n'est
> pas un détail de procédure : c'est la question qui a tué la stratégie 1.

### 3. Pourquoi l'effet n'a-t-il pas disparu ?

Sans réponse tant que la question 1 n'en a pas.

---

## ÉTAPE 2 — Les données : ce que ça coûte vraiment

| Source | Granularité | Historique | Prix | Verdict |
|---|---|---|---|---|
| yfinance 1 min | 1 min | **7 jours** | gratuit | inutilisable — 7 jours ne font pas un échantillon |
| yfinance 1 h | 1 h | 730 jours | gratuit | ~500 séances, trop gros grain pour du scalp |
| Alpha Vantage gratuit | 1 min | 2 ans | 0 € | **25 appels/jour** — un balayage d'univers est impossible |
| Alpha Vantage payant | 1 min | 20 ans+ | ~50 €/mois | utilisable |
| Autres fournisseurs | 1 min à tick | 10 ans+ | 30 à 200 €/mois | utilisable |

**Ce qu'il faut pour atteindre les 200 trades du critère 1**, en scalp :
quelques semaines suffisent en nombre. Mais 200 trades tirés de trois
semaines ne valident rien — ils couvrent un seul régime de marché. Il
faut **plusieurs années**, donc un historique payant.

### La question à trancher en premier

> **Es-tu prêt à payer environ 50 €/mois pendant au moins six mois pour
> découvrir si l'hypothèse tient ?**

600 € pour une réponse qui a de bonnes chances d'être « non ». C'est un
investissement raisonnable *si* la question 2 de l'étape 1 a une réponse.
C'est de l'argent jeté si elle n'en a pas.

---

## ÉTAPE 3 — Ce que le programme devra apprendre à faire

Aucun de ces points n'est difficile, mais aucun n'existe aujourd'hui.

| Chantier | Pourquoi |
|---|---|
| Collecteur intraday + cache | `cache.py` ne connaît que le journalier |
| Contrôle qualité intraday | `qualite.py` raisonne en séances, pas en minutes |
| Séances partielles, préouverture, after-hours | une bougie de 9 h 30 n'est pas une bougie de 15 h |
| Fuseaux horaires et heure d'été | une erreur d'une heure décale tous les signaux |
| Frais réalistes par aller-retour | le paramètre qui décide de tout |
| Rejeu tick par tick | le moteur actuel suppose une barre par jour |

Comptez **plusieurs soirées de travail** avant le premier chiffre.

---

## ÉTAPE 4 — Ce qui existe DÉJÀ et répond à une partie du besoin

`horizon.py`, livré aujourd'hui, mesure sur vos données actuelles :

- l'**amplitude** du titre à 1 jour, 1 semaine, 2 semaines, 1 mois,
  3 mois, 6 mois et 1 an ;
- **quel objectif de prise de profit** ce titre a réellement atteint dans
  le passé, en combien de séances, et combien de fois il a tout rendu
  ensuite.

Ce n'est pas du scalp. Mais l'horizon « 1 jour » y est, et il dit une
chose utile avant de payer quoi que ce soit : **de combien ce titre bouge
en une séance**. Si l'amplitude typique à 1 jour est de 1,2 % et que
l'aller-retour coûte 0,30 %, un quart du mouvement part en frais avant
d'avoir eu raison.

    py -m equity_scanner.horizon NVDA

---

## L'ordre dans lequel avancer

| # | Étape | Qui | Durée |
|---|---|---|---|
| 1 | Regarder l'amplitude à 1 jour sur tes titres | toi, `H` au menu | 10 min |
| 2 | Répondre à la question 2 : **qui est en face ?** | toi | la vraie difficulté |
| 3 | Si et seulement si 2 a une réponse : choisir une source de données | à deux | 1 soirée |
| 4 | Écrire `intraday-v1.md`, le geler, le hacher | moi | 1 soirée |
| 5 | Collecteur, cache, contrôle qualité intraday | moi | plusieurs soirées |
| 6 | Vérification technique sur données anciennes | moi | 1 soirée |
| 7 | **Validation, un seul passage** | moi | 1 h |

**L'étape 2 est la seule qui compte.** Les autres sont du travail ; celle-là
est la question à laquelle la stratégie 1 n'a pas su répondre, et c'est
pour ça qu'elle est morte en Phase 0.

---

*Ce document ne propose aucune règle et ne gèle aucun paramètre. Il dit ce
qu'il faut savoir avant d'en écrire. Tant qu'il n'est pas remplacé par un
`intraday-v1.md` daté et haché, aucun signal intraday ne sortira de ce
programme.*
