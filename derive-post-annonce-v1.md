# DÉRIVE POST-ANNONCE — SPÉCIFICATION v1.0
### Hypothèse n°2 du registre · rédigée le 15 septembre 2026
### **Paramètres gelés à la rédaction. Aucune valeur ne bouge après ce document.**

---

## ÉTAPE 1 — L'hypothèse économique

Les trois questions du protocole. Si une seule reste sans réponse, on
s'arrête.

### 1. Quel comportement exploite-t-on ?

L'**attention limitée** et la **sous-réaction**. Quand une entreprise
publie des résultats très au-dessus ou très en-dessous de ce qui était
attendu, le prix bouge le jour même — mais pas assez. L'information met
des semaines à être entièrement intégrée, parce que la majorité des
acteurs ne réagit pas le jour de la publication.

S'y ajoute l'**effet de disposition** : les détenteurs vendent leurs
gagnants trop tôt pour encaisser, ce qui freine mécaniquement la montée
et l'étale dans le temps.

### 2. Qui est de l'autre côté, et pourquoi accepte-t-il de perdre ?

Trois populations, et aucune n'est mieux informée que toi :

**Les vendeurs par prise de profit.** Ils vendent après une bonne
surprise parce qu'ils ont un gain à réaliser, pas parce qu'ils jugent
le titre cher. Leur décision ne porte aucune information.

**Les fonds indiciels.** Ils rééquilibrent à date fixe, sans
considération de prix. Ils vendent ce qui a monté pour revenir à leur
pondération cible.

**Les fonds à mandat de style.** Un fonds « value » doit vendre un titre
devenu trop cher selon ses critères, même s'il pense qu'il va monter.
C'est une contrainte, pas une opinion.

### 3. Pourquoi l'effet n'a-t-il pas disparu ?

Il s'est **affaibli**, c'est documenté, et il faut le dire. Mais trois
raisons expliquent qu'il survive :

Il faut tenir la position plusieurs semaines à travers du bruit — la
plupart des acteurs n'en ont pas la patience. La capacité est limitée :
un fonds de plusieurs milliards ne peut pas exploiter une dérive sur une
capitalisation moyenne sans déplacer le prix contre lui. Et les frais de
rotation le rendent non rentable au-dessous d'une certaine taille de
surprise.

> **Réserve honnête** : l'affaiblissement de l'effet depuis vingt ans
> est réel. C'est précisément ce que le test doit trancher, pas ce que
> le document doit supposer.

---

## ÉTAPE 2 — Les règles, gelées

### Mesure de la surprise

On n'utilise **pas** la surprise comptable sur le bénéfice par action.
Raison pratique : les estimations d'analystes historiques ne sont pas
accessibles avec les données dont on dispose, et bricoler une
approximation introduirait un biais invisible.

On utilise la **réaction du marché lui-même** :

> **CAR3** = rendement du titre moins rendement de l'indice, cumulé sur
> les 3 séances allant de la veille de l'annonce au lendemain
> (J−1, J, J+1).

C'est la mesure standard en l'absence de données d'estimations. Elle a
un avantage : elle intègre déjà tout ce que le marché a jugé important,
pas seulement le chiffre du bénéfice.

### Conditions d'entrée

Toutes vraies, évaluées à la **clôture de J+2**, exécution à
**l'ouverture de J+3** :

| # | Condition | Seuil |
|---|---|---|
| E1 | CAR3 | **≥ +5,0 %** |
| E2 | Volume du jour d'annonce / moyenne 20 j | **≥ 2,0** |
| E3 | Clôture de J+1 | **au-dessus** de la clôture de J−1 |
| E4 | Prix | **≥ 10 €/$** |
| E5 | Volume en devise sur 20 j | **≥ 20 M** |
| E6 | Indice de référence | **au-dessus de sa MM200** |

E1 et E2 définissent la surprise. E3 écarte les cas où le marché s'est
ravisé dès le lendemain. E4, E5, E6 sont les vetos déjà en place.

### Conditions de sortie

Dans l'ordre, la première atteinte ferme :

| # | Condition | Valeur |
|---|---|---|
| S1 | Durée maximale | **45 séances** |
| S2 | Stop sur clôture | **entrée − 2,0 × ATR(14)** |
| S3 | Annonce suivante | sortie la **veille** |
| S4 | Régime | indice sous sa MM200 |

**Aucun take-profit.** C'est la leçon de l'échec v3.3 d'Alfred : zéro
take-profit touché, 97 % de sorties par autre chose. Un take-profit
coupe la dérive exactement là où elle produit son rendement.

La durée de 45 séances vient de la littérature — la dérive se
concentre sur les 60 jours calendaires qui suivent. Elle n'a pas été
choisie en regardant un résultat.

### Dimensionnement

Identique au système précédent, pour que la comparaison ait un sens :
1 % de risque par trade, 10 positions simultanées au maximum, 25 % du
sleeve par ligne, coupe-circuit à −6 % sur un mois.

Dix positions au lieu de cinq : la dérive est un effet de portefeuille,
pas de titre. Sur un seul titre elle est noyée dans le bruit.

---

## ÉTAPE 3 — Séparation des données

| Période | Rôle | Regards autorisés |
|---|---|---|
| 2010 – 2021 | Vérification technique du code | illimités |
| 2022 – 2026 | **Validation** | **un seul** |

---

## ÉTAPE 4 — Le problème des données, sans le contourner

C'est le point dur, et il faut le regarder en face.

**Ce qu'il faut** : les dates historiques de publication de résultats,
pour chaque titre, sur 2022–2026.

**Ce qu'on a** : `yfinance` expose les dates de publication sur
généralement 4 à 8 trimestres en arrière. Alpha Vantage donne le
calendrier à venir, pas l'historique complet, et son quota de 25 appels
par jour interdit de balayer un univers.

**Trois voies, avec leurs coûts :**

**A. Se limiter à ce que yfinance donne.** Deux ans d'historique, environ
8 trimestres. Sur 400 titres, cela ferait de l'ordre de 3 200 événements,
dont peut-être 10 à 15 % passent le filtre CAR3 ≥ 5 % — soit **320 à 480
trades**. Au-dessus du minimum de 200. Faisable immédiatement, mais la
période de validation se réduit à 2024–2026.

**B. Acheter un historique de dates d'annonces.** Quelques dizaines
d'euros par mois chez un fournisseur de données. Permet de remonter à
2010 et de faire un vrai walk-forward.

**C. Reconstituer les dates par détection de saut de volume.** Non. Cela
introduit un biais qu'on ne saurait pas mesurer, et qui irait
précisément dans le sens de l'effet recherché.

> **Recommandation : voie A pour le premier test.** Si le z sort positif
> avec assez de trades, la voie B devient un investissement justifié.
> S'il sort à zéro, on a économisé l'abonnement.

---

## ÉTAPE 5 — Les cinq critères

Inchangés. Tous doivent passer, sur la période de validation touchée
une seule fois.

| # | Critère | Seuil |
|---|---|---|
| 1 | Nombre de trades | ≥ 200 |
| 2 | Profit factor | ≥ 1,15 |
| 3 | Espérance après coûts | > 0 |
| 4 | **Score z contre entrées aléatoires** | **≥ 2** |
| 5 | Drawdown maximal | < 20 % |

### Le contrôle par entrées aléatoires, adapté

Pour cette stratégie, le tirage aléatoire ne doit **pas** être une date
au hasard. Il doit être **une autre date d'annonce**, choisie au hasard
parmi les annonces sans surprise.

Sinon on ne teste pas la bonne chose : on comparerait « acheter après
une surprise » à « acheter n'importe quand », ce qui mélange l'effet
cherché avec le simple fait d'acheter après une publication.

---

## ÉTAPE 6 — Sensibilité aux coûts, obligatoire

Le tableau est déjà dans le moteur. Quatre hypothèses :

| Hypothèse | Ce qu'elle teste |
|---|---|
| Clôture du jour, sans frais | irréaliste, sert de plafond |
| Ouverture J+1, sans frais | décalage seul |
| J+1 + 0,15 % par côté | conditions normales |
| **J+1 + 0,30 % par côté** | **conditions défavorables** |

**Si l'avantage ne survit pas à la dernière ligne, il n'existe pas.**

Mesuré sur le système précédent : entre la première et la troisième
ligne, 92 % de l'espérance disparaissait.

---

## ÉTAPE 7 — La barre économique

Battre SMH acheté et conservé, **net de tout** :

| Horizon | Rendement brut nécessaire pour égaler |
|---|---|
| 5 ans | **17,14 %** |
| 10 ans | **18,28 %** |

Un GO technique qui ne franchit pas cette barre est un **non**
économique. Il ne se déploie pas.

---

## ÉTAPE 8 — Ce qui se passe après le résultat

**GO** — déploiement sur le sleeve, plafonné à 25 % du portefeuille.

**NO-GO** — l'hypothèse est morte. Pas retouchée, pas assouplie.
**Exception unique** : si le critère 1 échoue (moins de 200 trades) avec
un z positif, on élargit l'échantillon — voie B des données — **sans
toucher à une seule règle**.

---

## Le plan d'attaque, dans l'ordre

| # | Étape | Durée | Livrable |
|---|---|---|---|
| 1 | Collecte des dates d'annonces sur l'univers US large | 2 h de machine | fichier de dates |
| 2 | Calcul du CAR3 pour chaque événement | 20 min | table des surprises |
| 3 | Vérification du code sur 2010–2021 | 1 soirée | trades cohérents |
| 4 | **Validation sur 2022–2026, un seul passage** | 1 h | les cinq critères |
| 5 | Sensibilité aux coûts | inclus | tableau à quatre lignes |
| 6 | Comparatif contre SMH net de PFU | inclus | verdict économique |
| 7 | Inscription au registre, résultat compris | 5 min | ligne datée |

---

## À inscrire au registre AVANT de lancer

```
| date       | hypothèse           | empreinte SHA256 | univers  | période   | résultat | z |
| 15/09/2026 | Dérive post-annonce | (à calculer)     | US large | 2024-2026 | en cours | — |
```

Empreinte à calculer avant le premier test :

```
certutil -hashfile derive-post-annonce-v1.md SHA256
```

---

*Ce document ne prédit rien. Il fixe ce qu'on va mesurer, comment, et
ce qui comptera comme réponse — avant d'avoir vu le résultat. C'est la
seule chose qui rend le résultat croyable.*
