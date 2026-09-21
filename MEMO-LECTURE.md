# Mémo de lecture — tous les seuils de CARRUOS

Ce document est la **carte des seuils**. Chaque nombre qu'affiche le
programme vient d'une des constantes ci-dessous, et chacune est nommée
ici avec l'endroit du code où elle vit.

`test_moteur` vérifie que **chaque nombre écrit dans ce mémo est celui
qui tourne réellement**. Un mémo qui dérive du code est pire qu'aucun
mémo : il donne confiance dans un chiffre faux.

> Deux mots avant de lire. Les seuils de **stratégie** (§1, §2) sont
> **gelés** : ils ont été fixés avant leur test, avec une empreinte
> SHA256. Les seuils de **lecture** (§4) ne sont pas une stratégie : ils
> définissent ce qu'une forme *est*, pas ce qu'il faut en faire. Aucun
> des deux ne se retouche après avoir regardé un résultat.

---

## 1. Les indicateurs — `indicators.py`, **GELÉS**

| Indicateur | Réglage | Ce que ça veut dire |
|---|---|---|
| RSI | **14** séances | force du mouvement, de 0 à 100 |
| MACD | **12 / 26 / 9** | deux moyennes exponentielles et leur signal |
| Bollinger | **20** séances, **2** écarts-types | couloir de volatilité autour de la moyenne |
| SMA longue | **200** séances | la ligne de partage tendance haussière / baissière |
| SMA moyenne | **50** séances | la tendance intermédiaire |
| EMA courte | **20** séances | le niveau autour duquel un repli sain revient |
| ATR | **14** séances | l'amplitude moyenne d'une séance, en euros ou dollars |
| Moyenne de volume | **20** séances | la référence du RVOL |
| Pente de la SMA50 | sur **20** séances | la tendance de la tendance |
| Plus haut de référence | **60** séances | d'où se mesure un repli |
| Volume dollar | moyenne **20** séances | la liquidité réelle |

**Ces onze valeurs ne se modifient pas.** Les changer après coup
transforme un test en recherche. Il faudrait une nouvelle
spécification, une nouvelle empreinte et une période vierge.

---

## 2. Les 13 blocs d'entrée — `rules.py`, **GELÉS**

### Bloc 1 — le régime (5 conditions)

| # | Condition | Seuil |
|---|---|---|
| 1a | l'indice est au-dessus de sa MM200 | clôture > SMA 200 |
| 1b | le titre est au-dessus de sa MM200 | clôture > SMA 200 |
| 1c | la tendance 50 j monte | pente SMA50 sur 20 séances **> 0** |
| 1d | le titre surperforme l'indice | force relative > sa moyenne 50 |
| 1e | MACD en territoire positif | **ligne** MACD **> 0** |

> La **ligne** MACD, pas l'histogramme. L'histogramme passe négatif par
> construction dès qu'il y a repli : l'exiger positif à l'entrée arrive
> 4 à 6 séances après le point bas et tue le setup.

### Bloc 2 — le repli (4 conditions)

| # | Condition | Seuil |
|---|---|---|
| 2a | replié au bon niveau | écart à l'EMA20 ≤ **0,5 × ATR**, ou passage sous la moyenne de Bollinger |
| 2b | RSI passé dans la zone d'achat | au moins une valeur entre **40 et 55** sur **10** séances |
| 2c | le repli est resté sain | le RSI n'est **jamais** descendu sous **40** |
| 2d | le repli est récent | au plus **10** séances depuis le plus haut 60 j |

> La zone d'achat est **40–55**, pas 30. Un RSI à 30 en tendance
> haussière veut dire que la tendance est cassée, pas qu'il y a une
> affaire à faire.

### Bloc 3 — le déclencheur (3 conditions)

| # | Condition | Seuil |
|---|---|---|
| 3a | le momentum se retourne | histogramme MACD > celui de la veille |
| 3b | clôture au-dessus de l'EMA20 | clôture > EMA 20 |
| 3c | dépasse le plus haut de la veille | clôture > plus haut de la veille |

### Bloc 4 — la confirmation (1 condition)

| # | Condition | Seuil |
|---|---|---|
| 4a | volume confirmé | RVOL ≥ **1,20** |

### Les 4 conditions de sortie

| Condition | Seuil |
|---|---|
| marché sous sa MM200 | l'indice passe sous sa SMA 200 |
| 2 clôtures sous l'EMA20 | deux séances de suite |
| clôture sous la SMA50 | une seule suffit |
| MACD repassé négatif | ligne MACD < 0 |

> La spécification ferme à la **première** condition atteinte.
> Aucun take-profit : zéro TP touché au test, 97 % de sorties par
> autre chose.

### Les vetos — c'est ça, « HORS CRITÈRES »

Un veto **interdit** l'entrée quel que soit le nombre de blocs qui
passent. Ce n'est pas un jugement sur le cours, c'est un filtre
d'éligibilité.

| Veto | Seuil | Pourquoi |
|---|---|---|
| prix trop bas | < **10 $** | l'écart achat-vente mange le gain |
| liquidité insuffisante | volume dollar 20 j < **20 M$** | tu ne peux pas sortir sans bouger le cours |
| mouvement de nouvelle | gap > **5 %** sur **3** séances | le mouvement ne vient pas du repli |
| ligne déjà détenue | position ouverte sur ce titre | pas deux fois la même |
| portefeuille plein | **5** positions ouvertes | le plafond de la spécification |
| annonce proche | résultats dans < **10** séances | on ne traverse pas une annonce |

### Le dimensionnement

| Règle | Valeur |
|---|---|
| risque par trade | **1 %** du sleeve |
| stop | le plus bas entre (plus bas du repli − **0,1 × ATR**) et (entrée − **1,5 × ATR**) |
| plafond de poids par ligne | **25 %** du sleeve à l'achat, **20 %** à la vente |
| positions simultanées | **5** au maximum |

---

## 3. Le contrôle qualité des données — `qualite.py`

Un titre qui échoue à l'un de ces contrôles **ne produit aucun signal**,
et ressort toujours avec son motif.

| Contrôle | Seuil | Gravité |
|---|---|---|
| historique minimum | **220** barres (SMA200 + sa pente) | bloquant |
| trous dans la cotation | > **2 %** des séances ouvertes | bloquant |
| trou consécutif | > **5** séances d'affilée | bloquant |
| saut de cours suspect | \|ln(C/C₋₁)\| > **0,35** | bloquant (division non ajustée probable) |
| saut net du mouvement de l'indice | > **0,25** | bloquant |
| cours strictement plats | > **5** séances de suite | bloquant |
| volume nul | > **3** séances de suite | bloquant |
| fraîcheur | dernière barre > **5** séances ouvrées | bloquant sur un scan |
| désynchronisation avec l'indice | > **5** séances d'écart | bloquant |
| dates communes avec l'indice | < **90 %** | bloquant |

---

## 4. La lecture des chandeliers — `chandeliers.py`

**Ce ne sont pas des règles d'entrée.** Aucune figure n'entre dans les
13 blocs. Ce sont des définitions géométriques, écrites avant toute
mesure, pour que le mot « marteau » veuille dire la même chose à chaque
fois.

### Les grandeurs d'une bougie

```
étendue      = plus haut − plus bas
corps        = |clôture − ouverture|
ombre haute  = plus haut − le sommet du corps
ombre basse  = le bas du corps − plus bas
```

### Les seuils de forme

| Seuil | Valeur | Rôle |
|---|---|---|
| doji | corps ≤ **10 %** de l'étendue | ouverture et clôture quasi au même prix |
| petit corps | corps ≤ **35 %** | marteau, étoile filante |
| grand corps | corps ≥ **60 %** | harami, avalement, étoiles |
| marubozu | corps ≥ **90 %** | presque aucune ombre |
| ombre longue | ≥ **2 ×** le corps | ce qui fait la silhouette |
| ombre opposée | ≤ **15 %** de l'étendue | mesurée sur l'ÉTENDUE, pas sur le corps |
| corps dans le tiers | ≥ **66 %** de l'étendue au-dessus (ou en dessous) | marteau contre étoile filante |
| contexte | **±2 %** sur **5** séances | distingue marteau et pendu |
| barre trop étroite (relatif) | étendue < **0,3 × ATR** | aucune figure retenue |
| barre trop étroite (absolu) | étendue < **0,15 %** du cours | aucune figure retenue |

> **L'ombre opposée se mesure sur l'étendue, pas sur le corps.** Première
> version : « ≤ 1 × le corps ». Sur une étoile filante le corps fait 3 %
> de l'étendue, donc la règle exigeait une ombre opposée de moins de
> 3 % — aucune vraie bougie ne passait, et le détecteur n'a jamais
> trouvé ni étoile filante ni marteau inversé jusqu'à ce que ce soit
> corrigé.

### Les 17 figures reconnues

| Figure | Définition géométrique |
|---|---|
| **Doji** | corps ≤ 10 % de l'étendue |
| **Marubozu haussier** | corps ≥ 90 % de l'étendue, clôture au-dessus de l'ouverture |
| **Marubozu baissier** | corps ≥ 90 % de l'étendue, clôture en dessous de l'ouverture |
| **Marteau** | petit corps dans le tiers haut, ombre basse ≥ 2 × corps, ombre haute ≤ 15 % de l'étendue, **après une baisse de 2 % sur 5 séances** |
| **Pendu** | la même forme, **après une hausse** |
| **Étoile filante** | petit corps dans le tiers bas, ombre haute ≥ 2 × corps, **après une hausse** |
| **Marteau inversé** | la même forme, **après une baisse** |
| **Harami haussier** | corps de la 2ᵉ entièrement dans celui de la 1ʳᵉ ; 1ʳᵉ rouge et grande, 2ᵉ verte |
| **Harami baissier** | même emboîtement ; 1ʳᵉ verte et grande, 2ᵉ rouge |
| **Avalement haussier** | corps de la 2ᵉ contenant celui de la 1ʳᵉ ; 1ʳᵉ rouge, 2ᵉ verte et grande |
| **Avalement baissier** | même englobement, sens inverse |
| **Pénétrante** | 2ᵉ verte, ouvre sous le corps de la 1ʳᵉ (rouge), clôture au-dessus de son milieu |
| **Nuage noir** | 2ᵉ rouge, ouvre au-dessus du corps de la 1ʳᵉ (verte), clôture sous son milieu |
| **Étoile du matin** | grande rouge, petit corps, grande verte clôturant au-dessus du milieu de la 1ʳᵉ |
| **Étoile du soir** | grande verte, petit corps, grande rouge clôturant sous le milieu de la 1ʳᵉ |
| **Trois soldats blancs** | trois grands corps verts, chacun clôturant au-dessus du précédent |
| **Trois corbeaux noirs** | trois grands corps rouges, chacun clôturant sous le précédent |

### Comment lire le tableau de suivi

Pour chaque figure, le programme mesure ce qui a suivi **sur ce
titre**, à **1, 5, 10 et 20** séances, et le compare au **taux de
base** du titre.

- **taux de base** : la part de séances quelconques suivies d'une
  hausse à cet horizon. Sur un titre qui monte 55 % du temps, « 56 %
  de hausses après un marteau » ne dit rien.
- **écart** : taux de la figure moins taux de base, en points.
- **indiscernable** : l'intervalle de Wilson à 95 % **contient** le
  taux de base. Autrement dit, l'écart tient dans le bruit.
- **moins de 10 cas** : rien n'est publié. En dessous, l'intervalle
  couvre à peu près tout.

### Le piège qu'il faut connaître

17 figures × 4 horizons + 4 états de volume × 4 horizons ≈ **72
mesures par titre**. L'intervalle est à 95 %, donc **une mesure sur
vingt tombe à côté par construction** : environ **4 « écart net » sont
attendus sur chaque titre même s'il n'y a rien à trouver**.

Vérifié : sur **12 univers de cours purement aléatoires**, où il n'y a
rien à trouver par construction, **4,5 %** des mesures ressortaient en
« écart net » — contre 5 % attendus. Le module ne fabrique pas
d'avantage.

**Un écart net isolé ne vaut rien.** Ce qui compterait, ce serait la
même figure nette sur **plusieurs horizons à la fois** et sur
**plusieurs titres**.

---

## 5. Volume et prix — et l'open interest

**Une action n'a pas d'open interest.** C'est une notion de contrats à
terme et d'options : le nombre de contrats ouverts non dénoués. Une
action existe en nombre fixe ; il n'y a rien à ouvrir ni à dénouer.
Tout site qui affiche un « open interest » sur une action affiche autre
chose.

Ce qui joue le même rôle sur une action, c'est le **volume rapporté à
son habitude** (le RVOL). Le programme mesure les quatre états et ce
qui les a suivis, exactement comme pour les figures :

| État | Lecture traditionnelle | Ce que dit CARRUOS |
|---|---|---|
| hausse + volume ≥ 1,20 | « mouvement confirmé » | le taux mesuré et son écart au taux de base |
| hausse + volume < 1,20 | « mouvement non confirmé » | idem |
| baisse + volume ≥ 1,20 | « baisse confirmée » | idem |
| baisse + volume < 1,20 | « baisse non confirmée » | idem |

L'open interest des **options** d'une action existe, lui, et se lit
séparément — voir `options.py`.

---

## 5 bis. MA LISTE — comment le classement est fait

Vous collez des tickers, chacun passe les **13 blocs** et les **vetos**,
puis se range dans son groupe : *les 13 blocs passent*, *il manque un ou
deux blocs*, *signal absent*, *conditions de sortie actives*, *hors
critères*, *données insuffisantes*, *données refusées*, *non lisibles*.

### L'ordre à l'intérieur d'un groupe

| Tri | Sur quoi il range |
|---|---|
| **spécification** (défaut) | force relative à 6 mois — c'est `rules.rank()` |
| blocs | le plus de blocs remplis d'abord |
| risque | le risque le plus faible d'abord |
| mesure | le R moyen mesuré sur ce titre, le plus élevé d'abord |
| alphabétique | par ticker |

> Le tri par défaut porte son propre avertissement, écrit dans le code
> de la spécification : c'est un **départage**, pas un signal validé, et
> il ajoute un degré de liberté qui n'a pas passé la Phase 0. Chacun des
> quatre autres range sur **un seul fait**. Aucun n'additionne des
> critères pondérés : un tri sur un fait se vérifie, une somme de poids
> inventés non.

### Le « ratio risque / gain »

**Il n'existe pas**, et ce n'est pas un oubli : la spécification n'a
**aucun objectif de gain**, elle dit « aucun take-profit ». Il n'y a
donc pas de numérateur à mettre au-dessus du risque.

Ce qui est affiché à la place, et qui se vérifie :

| Côté risque | Côté résultat |
|---|---|
| `(entrée − stop) / entrée` en % | gagnants / trades **sur ce titre** |
| le nombre de titres et le montant | l'intervalle de Wilson de ce taux |
| la perte en euros si le stop saute | le R moyen et le profit factor |

Le côté droit est un **relevé du passé sur une hypothèse qui a rendu
NO-GO en Phase 0**. Il est là parce qu'il est vérifiable, pas parce
qu'il est encourageant.

### Le découpage des tickers

`COIN HOOD TLX.DE` et `COIN.TLX.HOOD.EPXD` marchent tous les deux. Le
point est ambigu — il sépare dans le second cas mais fait partie du
ticker dans `MC.PA`. Le programme ne devine pas : il **demande aux
données** si chaque découpage possible existe, et garde celui dont tous
les morceaux se chargent. `COIN.HOOD.MC.PA.TLX.DE` donne bien
`COIN`, `HOOD`, `MC.PA`, `TLX.DE` — alors qu'une règle syntaxique aurait
produit `HOOD.MC` (`.MC` est le suffixe de Madrid).

---

## 6. Ce que le programme refuse d'afficher

Rappel, parce que c'est la colonne vertébrale du projet :

- un pourcentage seul de « chances de gagner » — toujours l'intervalle
  de Wilson avec le nombre de trades ;
- un avis « garder / vendre » — le compte des conditions, jamais le
  verbe ;
- une « meilleure heure » pour passer un ordre — il faudrait des
  données intraday que le programme n'a pas ;
- un score composite sur des poids non testés, ni le verdict
  directionnel qu'on en tirerait ;
- une prédiction de prix — le cône de dispersion a sa dérive fixée à
  **zéro** : il donne l'amplitude, jamais le sens ;
- un take-profit actif ;
- un gain espéré en euros tant qu'aucune hypothèse n'a passé sa
  Phase 0.

---

## 7. Où en est la validation

| Hypothèse | État |
|---|---|
| Stratégie 1 — repli en tendance | **NO-GO** en Phase 0 sur S&P 500 et 120 titres US. Hypothèse morte. |
| Stratégie 2 — dérive post-annonce | spécifiée, moteur codé, **test pas encore lancé** |
| Stratégie 3 — dérive post-annonce négative (vente à découvert) | spécifiée, moteur codé, **test pas encore lancé**. Le dividende dû au prêteur n'est pas modélisé : retrancher ~0,4 point par trade. |

**Tant qu'aucune hypothèse n'a passé sa Phase 0, toute sortie de
CARRUOS est une liste de surveillance, pas une liste d'ordres.**
