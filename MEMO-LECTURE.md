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

## 5 ter. Poser une question en français

Le majordome (le disque en bas à droite) comprend des questions sur un
titre. Il ne réfléchit pas : il **reconnaît ce qui est demandé** et va
chercher la section de faits correspondante.

| Ce que vous tapez | Ce qu'il sort |
|---|---|
| *que penses-tu de TLX* | la fiche complète — blocs, manques chiffrés, conditions de sortie |
| *je sors quand sur TLX* | les 4 conditions de sortie et leur état, le stop, le coût fiscal |
| *je peux renforcer ?* | les 13 blocs, ce qui manque, les vetos, la taille de ligne |
| *combien je peux perdre sur COIN* | entrée, stop, risque par titre, nombre de titres, perte en euros |
| *une figure sur HOOD ?* | les figures de la dernière bougie et ce qu'elles ont été suivies de |
| *ça bouge combien* | l'amplitude par horizon, sans direction |
| *les données sont fiables ?* | le verdict du contrôle qualité et ses motifs |
| *à quelle heure ferme la bourse* | les horaires de la place du titre |

> **« Que penses-tu de » ne rend pas un avis.** C'est le piège de ce
> genre d'outil : la question invite à inventer. Ici l'intention *avis*
> rend la **fiche complète**, et chaque réponse se termine par le rappel
> qu'aucune hypothèse n'a passé sa Phase 0.

**La règle qui rend la chose honnête :** rien n'est *rédigé* à la
volée. Les phrases sont des gabarits remplis avec les chiffres du
dossier, et le dossier ne contient que ce que les autres modules ont
déjà calculé. **Si un chiffre n'est pas dans le dossier, aucune phrase
ne peut le sortir** — et `test_moteur` le vérifie en passant un dossier
vide à chaque section.

Si vous ne nommez pas de titre, celui du champ ANALYSER sert de défaut.

---

## 5 quater. Le profil d'un instrument — `profil.py`

Une action et un ETF monde ne se lisent pas pareil, et la différence se
**mesure**. Aucun de ces chiffres n'est un avis, et aucun n'est résumé
en un score.

| Mesure | Ce que c'est |
|---|---|
| Volatilité annualisée | écart-type des rendements quotidiens, multiplié par la racine de **252** séances |
| Écart quotidien ordinaire | la volatilité ramenée à un jour. Deux séances sur trois tiennent dedans — arithmétique, pas prévision |
| ATR 14 rapporté au cours | l'amplitude moyenne d'une séance, en pourcentage |
| Pire recul depuis un sommet | sa profondeur, sa date, et **le temps qu'il a mis à être rattrapé** — ou qu'il n'a pas encore mis |
| Séances à plus de 5 % | combien, sur combien |
| Bêta et corrélation au repère | les deux ensemble : un bêta de 1,2 avec une corrélation de 0,2 veut dire « bouge fort ET ailleurs » |
| Durée mesurée des positions | les règles de la spécification rejouées sur tout l'historique, et la durée des trades obtenus |

Les bandes d'amplitude sont écrites **avant** toute mesure, et chaque
nom décrit ce qui a été mesuré — jamais ce qu'il faudrait en faire :

| Volatilité annualisée | Bande |
|---|---|
| sous **8 %** | TRÈS CALME |
| **8** à **16 %** | CALME |
| **16** à **25 %** | AMPLITUDE MOYENNE |
| **25** à **40 %** | AGITÉ |
| **40** à **65 %** | TRÈS AGITÉ |
| au-delà de **65 %** | AMPLITUDE EXTRÊME |

Sous **120** barres, aucune volatilité n'est affichée : un écart-type
sur trente points est lui-même trop imprécis pour valoir un chiffre.

Le type — action, ETF, indice — est **déclaré** par la source de
données, et le rapport le dit. Un ETF mal étiqueté reste mal étiqueté ;
les mesures, elles, ne dépendent d'aucun libellé.

**L'horizon n'est pas un choix.** C'est une conséquence des quatre
conditions de sortie : sur un instrument calme elles se déclenchent
rarement, donc les positions durent ; sur un instrument à forte
amplitude elles se déclenchent vite. C'est ce que la ligne « durée
mesurée » rapporte, et c'est la seule réponse honnête à « court ou long
terme ? ».

---

## 5 quinquies. Un objectif chiffré — `objectif.py`

**L'arithmétique ne dit jamais « impossible ». Elle dit ce que ça
demande.**

Pour aller d'un capital à une cible il n'existe que trois leviers : le
capital, le versement, et le taux avec le temps qu'on lui laisse. Deux
sont fixés, le troisième se résout — exactement, parce que c'est une
équation.

| Sortie | Ce que c'est |
|---|---|
| Sans aucune croissance | la durée par les seuls versements. **Le seul chiffre qui ne dépende d'aucune hypothèse.** |
| Taux exigé | ce que l'équation réclame pour tenir la date. Pas ce qu'un placement va rendre, et le programme ne dit pas où le trouver |
| Taux exigé net d'impôt | pour que la cible **reste** après le prélèvement forfaitaire de **30 %** sur le gain |
| Versement exigé | à 4, 7, 10 et 15 % par an posés en hypothèse |
| Durée au taux posé | votre hypothèse, ses conséquences |

Le taux net **ne se déduit pas** d'une division par (1 − 30 %) : le
prélèvement frappe le gain **une fois, à la sortie**, pas chaque année.
Sur un exemple mesuré — 8 000 € de capital, 300 € par mois, 50 000 € en
trois ans — l'équation donne **66,9 %** par an là où le raccourci
donnait 74,2 %. Et ce chiffre est un **plancher** : il suppose un seul
dénouement à la fin, alors que revendre souvent coûte plus.

Le versement est fait en **début de mois**, donc il travaille le mois
même — c'est la convention d'un virement programmé. Le taux mensuel est
celui qui vérifie (1 + m)¹² = 1 + a : diviser par douze serait faux, et
l'erreur grandit avec le taux.

Au-delà de **1200** mois, la réponse utile n'est plus un nombre
d'années : c'est « ces leviers-là n'y mènent pas », et les leviers se
changent.

La **fréquence historique** confronte le taux exigé à l'historique d'un
titre : quelle part des fenêtres de même durée l'ont atteint, avec son
intervalle de Wilson. Les fenêtres glissent, donc elles se recouvrent
presque entièrement — le nombre de périodes **indépendantes** est bien
plus petit, il est affiché, et c'est lui qui porte l'information. Une
fréquence passée n'est pas une probabilité future.

---

## 5 sexies. Le carnet — `carnet.py`

Deux choses distinctes, qui ne se mélangent pas.

**Vos notes.** Du texte libre, daté, rattachable à un titre. Le
programme n'y touche pas, ne les interprète pas, ne les résume pas, et
ne dira jamais « vous aviez raison ce jour-là » : comparer une intention
à un résultat demanderait de décider ce qui compte comme réussite, ce
qui est un avis.

**Vos relevés.** Une photo datée de ce que le moteur mesurait à
l'instant où vous l'avez figée. Elle est calculée **côté serveur** :
prise dans le navigateur, elle photographierait ce que la page
*affichait* au lieu de ce que le moteur a *mesuré*.

Rangé dans `~/.carruos/carnet.json`, le seul endroit qui survive à une
mise à jour du programme. Écriture par fichier temporaire puis
remplacement : une coupure au milieu d'une sauvegarde laisse l'ancien
carnet entier. Plafond de **12000** entrées, la plus ancienne partant la
première — à une note par jour, trente ans.

---

## 5 septies. Le cerveau — `cerveau.py`

Le majordome peut parler à un modèle de langage. Le contrat est le même
que partout ici : **il met en phrases, il ne produit aucun chiffre.**

Trois garde-fous, dans cet ordre.

1. **Les faits d'abord.** La réponse déterministe est calculée **avant**
   tout appel réseau et s'affiche quoi qu'il arrive : clé absente, API
   en panne, réponse de travers. Le modèle ajoute de la prose
   par-dessus ; il ne remplace jamais les faits.
2. **Le modèle ne voit jamais les cours.** Il reçoit un dossier de faits
   déjà calculés, donc il ne *peut* pas « lire le graphique ».
3. **Les chiffres sont tracés.** Chaque nombre de la réponse est
   confronté au dossier envoyé, et ceux qui n'y figurent pas sont
   **nommés** à l'écran. Ce n'est pas un filtre : c'est une étiquette.

La tolérance de cette comparaison vaut **une demi-unité du dernier
chiffre écrit** : « 12 % » peut venir de 11,83 %, « 11,8 % » ne peut
venir que d'entre 11,75 et 11,85. C'est exactement ce que veut dire
arrondir.

**Aucune clé n'est embarquée**, et le programme ne peut pas en fabriquer
une. C'est la vôtre, prise chez le fournisseur, rangée dans
`~/.carruos/ia.json` — jamais dans le code, jamais dans le dépôt, jamais
dans l'archive. Le dossier envoyé est plafonné à **24000** caractères :
un modèle qui reçoit trente pages répond moins bien, plus lentement et
plus cher.

Sans clé, le majordome répond quand même. Tout ce qui précède est
calculé en local.

### Un dossier trop lourd est réduit, jamais coupé

Couper le texte au caractère près faisait tomber la **fin** du dossier —
le profil, la mémoire, la position détenue ; dans BRAIN 2.0, le
portefeuille entier. Désormais les longues listes sont
ramenées à **12**, puis 6, puis 3 éléments, les
longs textes à **600** caractères, et s'il le faut les sections les plus
lourdes sont retirées — en le disant au modèle et à l'écran. Les sections protégées (les 13 blocs, la revue de
sortie, la position, la mémoire, le portefeuille) ne sont ni retirées ni
raccourcies. Les chiffres se vérifient contre ce qui a été **envoyé**.

### Quand le cerveau ne répond pas

Le refus du fournisseur est dit en français, avec ce qu'il faut faire.
Le plus courant : **« la clé est bonne, mais votre compte API n'a pas de
crédit »**. L'abonnement Claude (claude.ai, Pro ou Max) et l'API sont
deux comptes séparés : l'abonnement ne donne aucun crédit API. On en
achète sur console.anthropic.com → Settings → Billing ; la clé n'a pas à
être recollée. Au moment de **BRANCHER**, la clé est essayée par une
question minuscule, et la bulle dit tout de suite si elle marche.

### La recherche Web

Les deux fournisseurs peuvent chercher sur le Web : **3** recherches au
plus par question, **8** sources au plus affichées sous la réponse. Les
chiffres d'une adresse Web ne sont pas comptés comme des mesures. Un
modèle qui refuse l'outil répond quand même, sans lui.

### La vue complète du majordome — `brain2.py`

L'ancienne page BRAIN 2.0, ouverte par **VUE COMPLÈTE** dans la bulle du
majordome (adresse `/majordome`). Le titre et le portefeuille ensemble. Les conditions de sortie sont
relevées pour **15** lignes au plus. Les poids sont des parts des
positions, dans chaque devise ; le plafond de **25 %** par ligne ne se
vérifie que si toutes les lignes sont dans une même devise — sans taux de
change, le programme le dit au lieu de comparer des euros à des dollars.

---

## 5 octies. La veille — `veille.py`

**Un rapprochement, pas une analyse.** Elle dit quelles actualités
rencontrent vos lignes. Elle ne dit pas ce que le cours va faire, ni
dans quel sens, ni quand.

Trois niveaux, du plus factuel au moins factuel, chacun étiqueté à
l'écran :

| Niveau | Ce que c'est | Force |
|---|---|---|
| **NOMMÉ** | la source déclare elle-même que l'article porte sur ce titre | un fait énoncé par le fournisseur |
| **MÊME SECTEUR** | le thème de l'article correspond au secteur **déclaré** de l'un de vos titres | une correspondance de **noms**, écrite d'avance |
| **MOT TROUVÉ** | le titre contient un mot d'une liste écrite d'avance | un appariement de **chaînes de caractères** |

À l'écran, un titre **nommé** s'affiche en plein, un titre du **même
secteur** en pointillés : la différence de force se voit sans avoir à
lire une légende.

### La table de correspondance

Elle est écrite **avant** tout usage et affichée avec le résultat, pour
qu'on puisse la contester :

| Thème de la source | Secteurs déclarés |
|---|---|
| `energy_transportation` | énergie, industrie, services aux collectivités |
| `finance` | finance |
| `life_sciences` | santé |
| `manufacturing` | industrie, matériaux |
| `real_estate` | immobilier |
| `retail_wholesale` | consommation cyclique, consommation de base |
| `technology` | technologie, communication |

Elle est délibérément **pauvre** : chaque thème ne pointe que vers les
secteurs qu'il nomme explicitement. On pourrait la rendre plus riche —
« l'énergie touche les transports, qui touchent la distribution » — mais
chaque maillon ajouté serait une supposition.

`economy_macro`, `economy_monetary`, `economy_fiscal` et
`financial_markets` ne pointent vers **rien** : ils concernent tout le
marché, donc les rattacher à un secteur particulier serait faux.

### Pourquoi le niveau 3 est le dernier

**Alpha Vantage n'étiquette pas la géopolitique.** Ses thèmes sont
économiques et sectoriels : il n'y a ni « conflit » ni « sanctions ». Un
rapprochement géopolitique ne peut donc s'appuyer sur aucune déclaration
de la source — il faut chercher les mots soi-même, et c'est nettement
plus faible. D'où le nom : « mot trouvé », pas « risque géopolitique ».

**Aucun total n'est calculé.** Compter des occurrences donnerait un
nombre qui ressemblerait à une mesure sans en être une.
`test_moteur` le vérifie : il retire du texte tout ce que la veille
**recopie** de la dépêche, puis exige qu'il ne reste **aucun** chiffre.
Vérifié par mutation — ajouter une ligne « exposition géopolitique :
37,5 / 100 » fait tomber le test.

### Positif / négatif : l'étiquette d'Alpha Vantage

Chaque actualité porte une pastille — **positif**, **plutôt positif**,
**neutre**, **plutôt négatif**, **négatif** — et, sur les titres que
l'article nomme, le ton **pour ce titre** (un article peut être négatif
dans l'ensemble et positif pour l'un d'eux).

C'est le mot **d'Alpha Vantage**, pas celui de CARRUOS : ses cinq
étiquettes traduites, ses seuils publiés (≤ −0,35 négatif ; ≤ −0,15
plutôt négatif ; < 0,15 neutre ; < 0,35 plutôt positif ; au-delà
positif). Le score brut est au survol. Il classe le **vocabulaire** de
l'article par un modèle dont nous ignorons les poids ; il ne dit pas où
va le cours, et une information publique y est déjà quand on la lit.

**Rien ne s'en sert** : ni règle, ni tri, ni compte, ni le rapprochement
avec vos lignes, ni le majordome. Affiché à votre demande, attribué à
chaque fois — `test_moteur` le vérifie.

Les lignes rapprochées sont vos **positions** et les titres que le
**carnet** connaît. MA LISTE ne se conserve pas d'une visite à l'autre,
donc elle n'alimente pas la veille.

---

## 5 nonies. L'onglet IBKR — `ibkr.py`

**CARRUOS lit votre compte ; il ne peut pas y passer d'ordre.** Pour
acheter ou vendre : IBKR.

### Brancher

**Aucun identifiant à donner.** CARRUOS ne demande ni votre numéro de
compte, ni votre nom d'utilisateur, ni votre mot de passe IBKR : vous
vous connectez dans TWS comme d'habitude, et CARRUOS lit ce que TWS lui
montre. **Le seul numéro qui compte est le port**, et la page le déduit
de deux questions.

0. Une fois : installer la bibliothèque — `py -m pip install ib_async`,
   ou Carruos.bat, choix 2, en répondant **o** à la question IBKR.
1. Une fois, dans TWS : **File → Global Configuration → API →
   Settings**. Cocher **Enable ActiveX and Socket Clients** et
   **Read-Only API** (un second verrou, côté IBKR), laisser cochée
   **Allow connections from localhost only**, vérifier le **Socket
   port**. Avec IB Gateway : **Configure → Settings → API → Settings**.
   Le pas-à-pas est aussi dans l'onglet, à droite.
2. Ouvrir TWS et s'y connecter — en **Paper Trading** pour commencer.
3. Dans l'onglet IBKR : répondre aux deux questions (**quel logiciel**,
   **quel compte**) — le port s'affiche en grand — ou cliquer
   **DÉTECTER AUTOMATIQUEMENT**, qui frappe aux quatre ports de cet
   ordinateur et choisit celui qui répond. Puis **CONNECTER**.

Les **réglages avancés** (adresse, port personnalisé, numéro de client)
n'ont rien à changer en temps normal. Le numéro de client est un numéro
de guichet entre CARRUOS et TWS, **pas** votre numéro de compte : on ne
le change que si TWS répond qu'il est déjà pris.

| Port | Programme | Compte |
|---|---|---|
| **7497** | TWS | simulation |
| **7496** | TWS | réel |
| **4002** | IB Gateway | simulation |
| **4001** | IB Gateway | réel |

Le libellé « simulation » ou « réel » en tête de page ne vient **pas**
du port : il se lit sur le numéro de compte (« DU… » pour la
simulation). Un compte réel s'affiche en or.

### Ce que « en direct » veut dire

Chaque cours porte son type, tel que TWS le déclare :

| Étiquette | Sens |
|---|---|
| **TEMPS RÉEL** | le compte a l'abonnement de données de cette place |
| **DIFFÉRÉ** | pas d'abonnement : 15 à 20 minutes de retard |
| **FIGÉ** | hors séance : le dernier cours connu |
| **FLUX DU COMPTE (≈ 3 MIN)** | aucun tick reçu : la valeur vient du flux « compte » d'IBKR, rafraîchi environ toutes les trois minutes |

La page se relit toutes les **2** secondes quand elle est au premier
plan, toutes les **15** sinon. Le titre de la fenêtre porte le nombre
de stops franchis — « (1) CARRUOS ALICE — IBKR » — pour se voir même quand on
regarde ailleurs.

TWS se relance tout seul une fois par jour : la liaison se reconnecte
d'elle-même, en attendant **3**, puis 6, 15, 30 et **60** secondes
entre deux essais.

### Stop franchi

La ligne passe en rouge quand le cours est sous le stop **que vous avez
inscrit** dans le registre — pas un stop calculé par le programme. Le
type du cours est rappelé à côté : un cours différé sous un stop n'est
pas la même information qu'un cours en temps réel sous ce stop.

### Rapprochement avec le registre

Trois listes : au compte mais absents du registre, au registre mais
absents du compte, quantités différentes. Le bouton **RECOPIER** crée ou
met à jour le registre local depuis le compte — quantité et prix de
revient — **en conservant vos stops**. Il n'efface rien, et rien ne part
vers IBKR.

Quand l'onglet est branché, la **veille** rapproche l'actualité des
lignes du compte lui-même, pas seulement de celles du registre.

---

## 5 decies. La mémoire — `memoire.py`

**Ce que le programme a dit, et ce qui a suivi.** Chaque état — oui ou
non, avec ses blocs manquants — est écrit dans le journal d'audit
**avant** que le titre ne bouge : au scan, à chaque question au
majordome, à chaque ouverture d'une page graphique. La mémoire va
chercher ensuite ce que le titre a fait **contre son marché** (SPY pour
un titre américain, ^STOXX pour un titre européen), à trois horizons
écrits d'avance : **5**, **20** et **60** séances.

### Le tableau à quatre cases

| | Le titre a battu le marché | Il ne l'a pas battu |
|---|---|---|
| **Le programme disait oui** | signal confirmé | faux signal |
| **Le programme disait non** | occasion manquée | piège évité |

Un filtre ne se juge que sur les **deux lignes ensemble** : il trie
seulement si le taux de réussite quand il dit oui dépasse nettement celui
quand il dit non.

### Deux précautions de comptage

- La même barre relevée deux fois (un scan, puis une consultation) ne
  compte **qu'une** fois : la première écriture, la plus éloignée de
  tout résultat connu.
- Deux relevés du même titre à trois jours d'écart partagent presque
  toute leur fenêtre : ce n'est pas deux preuves. Pour un même titre et
  une même réponse, **une observation par fenêtre** de l'horizon.

### Quand la mémoire rend-elle un verdict ?

Seulement si **deux mesures de l'incertitude l'accordent**, dans le même
sens :

1. les intervalles de Wilson du « oui » et du « non » ne se recouvrent
   pas ;
2. l'écart entre les deux taux reste du même côté de zéro quand on tire
   les **titres** au hasard, avec remise — **2000** tirages. Ce tirage
   respecte le fait qu'un même titre revient plusieurs fois.

Sur **200** journaux de pur bruit, où chaque titre a son propre taux de
réussite et sa propre fréquence de « oui », la règle rend moins de 1 %
de faux verdicts (le tirage seul en rendait 5,5 à 8,5 %). Un filtre qui
apporte vraiment 15 points est reconnu dans plus de trois cas sur
quatre. `test_moteur` refait cette mesure à chaque passage.

### Les occasions manquées, toujours en face des pièges évités

Les **6** plus fortes occasions manquées s'affichent à côté des **6**
pièges évités les plus profonds — **le même nombre des deux côtés,
toujours**, même quand l'une des colonnes est plus longue. Montrer les
seules fusées manquées, c'est reproduire l'oubli sélectif qu'on veut
corriger : on se souvient de l'action qui a explosé, pas des quarante au
profil identique qui se sont effondrées.

### Ce que chaque bloc a coûté et épargné

Pour chaque bloc, parmi les « non » où il était en échec : combien de
fusées il a écartées, combien de pièges. Une ligne n'est dite nette
qu'à partir de **10** cas, et quand son intervalle de Wilson exclut le
taux de base. Treize blocs, trois horizons : environ deux lignes
« nettes » sont attendues **par le seul hasard**.

### Vos ordres, face au programme

Vos exécutions sont lues sur IBKR (onglet branché) et écrites dans
`~/.carruos/executions-ibkr.jsonl`, sans doublon. Chaque achat est rangé
**avec** ou **contre** le signal — à condition qu'un état du programme
ait été relevé au plus **5** jours avant l'ordre. Un achat sans relevé
est compté à part : reconstituer aujourd'hui ce que le programme aurait
dit, ce serait le juger avec un regard qui connaît déjà la suite.

Pour que vos ordres aient presque toujours leur relevé, chaque exécution
qui arrive fait relever l'état du programme **à la clôture de la
veille** de l'ordre — les cours sont coupés avant le jour de l'ordre, et
rien de ce jour-là n'y entre. C'est la question que se pose la
spécification : elle décide à la clôture et exécute à l'ouverture
suivante. Le relevé se fait le jour même, jamais des semaines plus tard.

L'API d'IBKR ne rend que les exécutions du jour : la mémoire de vos
ordres commence au premier branchement.

### Ce que la mémoire ne fait pas

**Elle ne touche à aucun seuil.** Assouplir un filtre parce qu'une
action a explosé, c'est l'ajuster sur un passé qu'il connaît déjà ;
recommencé à chaque fusée, le filtre finit par ne plus rien filtrer.
Ce qu'elle révèle peut devenir l'idée d'une **nouvelle spécification**,
écrite avant son test, avec sa propre empreinte, sur une période que
personne n'a regardée. C'est ainsi qu'un système apprend sans se
mentir : entre deux spécifications, jamais en déplaçant la règle après
avoir vu le résultat. `test_moteur` vérifie que `memoire.py` ne modifie
l'attribut d'aucun module.

---

## 5 undecies. Le test de la stratégie 2 — `pead.py`

**Une surprise de résultats est-elle suivie d'une dérive ?** La
spécification (`derive-post-annonce-v1.md`) est gelée ; la façon dont le
moteur la lit est écrite à part, datée et hachée avant tout regard sur
la période de validation (`derive-post-annonce-v1-lecture.md`).

### Les six conditions d'entrée, évaluées à la clôture de J+2

| # | Condition | Seuil |
|---|---|---|
| E1 | surprise : titre moins indice, cumulé de J−1 à J+1 | **≥ +5 %** |
| E2 | volume de la séance J / moyenne 20 séances | **≥ 2** |
| E3 | clôture de J+1 au-dessus de celle de J−1 | pas de rétractation |
| E4 | prix | **≥ 10** |
| E5 | volume en devise sur 20 séances | **≥ 20 M** |
| E6 | indice au-dessus de sa MM200 | à J+2 |

**J est la première séance qui peut réagir** : une publication à
**16 h** ou après (heure de New York) est échangée la séance suivante.
Achat à l'ouverture de J+3.

### Les sorties, la première atteinte ferme

**45** séances ; clôture sous entrée − **2** × ATR ; la veille de
l'annonce suivante ; indice sous sa MM200. Aucun take-profit.

### Le passage unique

- **Préparation**, répétable : relevé et gel des dates d'annonces,
  comptes sur 2024–2026 sans aucun rendement, et répétition générale
  complète sur la période de conception.
- **Passage**, une seule fois : inscrit au registre **avant** le calcul,
  fermé avec son résultat **avant** l'affichage. Un second passage est
  refusé ; il faut le demander en toutes lettres, et le motif est écrit
  au registre comme second regard.
- Il ne part pas si l'univers compte moins de **450** titres, si les
  dates manquent pour plus de 10 % des titres (au moins **90 %** rendus),
  si moins de **80 %** sont exploitables, ou si l'heure n'est connue que
  pour moins de **50 %** des publications.
- Le z compare aux annonces **sans surprise**, rejouées avec les mêmes
  sorties : **1000** tirages. Moins de **20** annonces témoins, pas de z.

Les cinq critères se mesurent à 0,15 % de frais par côté ; un GO exige
en plus une espérance positive à 0,30 %. Puis il faut battre SMH net.

Le registre est `~/.carruos/registre-tests.md`, les rapports sont dans
`~/.carruos/strategie-2/`.

---

## 5 duodecies. Le majordome à l'écran — `majordome.py`

L'onglet **MAJORDOME** fait apparaître le cerf — l'hologramme de
l'accueil en petit, aux couleurs du thème —, bulle ouverte,
sur la page où l'on est ; bulle ouverte, il le range. **Toutes** les
fenêtres le suivent.

- Cliquer le cerf ouvre ou ferme la bulle ; **Échap** la ferme ;
  **RANGER** le retire de toutes les fenêtres.
- On le déplace par le cerf ou par l'entête de la bulle. Moins de
  **5** pixels de mouvement, c'est un clic. Sa place est retenue en
  proportion de la fenêtre, et les autres fenêtres le posent au même
  endroit.
- La bulle s'ouvre du côté où il y a de la place : au-dessus du cerf
  s'il est dans la moitié basse, en dessous sinon.
- Sur une page graphique, il parle du titre affiché ; sur l'accueil, de
  celui écrit dans « analyser un titre ».

Le contrat est celui du cerveau : les faits d'abord, la prose du modèle
par-dessus, chaque chiffre du modèle confronté au dossier.

## 5 terdecies. Le logo et le raccourci du Bureau

Le logo est **l'hologramme de l'accueil** — anneaux, cône de lumière,
socle, cerf lumineux — dans un **médaillon** sombre qui le détache de
n'importe quel fond d'écran. Le même dessin sert à l'onglet du
navigateur, à chaque fenêtre, au raccourci et au cerf du majordome.

Pour le poser sur le Bureau : la roue des réglages, **Créer le raccourci
« Carruos Alice »** — ou Carruos.bat, choix 3. Un double-clic lance
CARRUOS sans console. Relancer remplace le raccourci au lieu d'en
empiler un second ; l'ancien « CARRUOS » n'est retiré que s'il menait à
ce programme. Si l'ancien dessin s'affiche encore, clic droit sur le
Bureau, **Actualiser** : Windows garde les icônes en mémoire.

## 5 quattuordecies. Positif / négatif dans les actualités

Voir 5 octies : c'est l'étiquette d'**Alpha Vantage**, attribuée à
l'écran, et rien ne s'en sert.

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
  Phase 0 ;
- une occasion manquée affichée seule — toujours en face des pièges
  évités, en même nombre.

---

## 7. Où en est la validation

| Hypothèse | État |
|---|---|
| Stratégie 1 — repli en tendance | **NO-GO** en Phase 0 sur S&P 500 et 120 titres US. Hypothèse morte. |
| Stratégie 2 — dérive post-annonce | moteur relu et corrigé avant le passage (note de lecture datée et hachée), passage unique **préparé et verrouillé**, pas encore lancé : `py -m equity_scanner.pead` |
| Stratégie 3 — dérive post-annonce négative (vente à découvert) | spécifiée, moteur codé, **test pas encore lancé**. Son moteur lit encore la date du calendrier : à relire comme celui de la stratégie 2 avant tout passage. Le dividende dû au prêteur n'est pas modélisé : retrancher ~0,4 point par trade. |

**Tant qu'aucune hypothèse n'a passé sa Phase 0, toute sortie de
CARRUOS est une liste de surveillance, pas une liste d'ordres.**
