# DÉRIVE POST-ANNONCE NÉGATIVE — SPÉCIFICATION v1.0
### Hypothèse n°3 du registre · vente à découvert
### **Paramètres gelés à la rédaction. Aucune valeur ne bouge après ce document.**

---

## ÉTAPE 0 — Avertissement préalable, avant toute règle

Vendre à découvert n'est pas acheter à l'envers. Trois asymétries
changent la nature du pari, et elles sont énoncées ici **avant** les
règles pour qu'on ne puisse pas les découvrir après un mauvais
résultat.

**1. La perte n'est pas bornée.** Sur un achat, le pire est de perdre
la mise : le titre vaut zéro. Sur une vente à découvert, il n'existe
aucune borne supérieure au prix. Un titre qui double coûte 100 % de la
position ; un titre qui quintuple en coûte 400 %. Le stop protège d'un
mouvement ordinaire, pas d'un écart d'ouverture.

**2. La position grossit quand elle a tort.** Un achat perdant pèse de
moins en moins lourd dans le portefeuille. Une vente à découvert
perdante pèse de plus en plus. Le plafond de 20 % par ligne doit donc
être vérifié **en continu**, pas seulement à l'entrée.

**3. Le marché dérive à la hausse.** Sur longue période, les indices
actions montent. Le vendeur à découvert nage à contre-courant du
rendement de marché : il ne suffit pas d'avoir raison sur le titre, il
faut avoir suffisamment raison pour couvrir cette dérive.

Une stratégie longue et son miroir court n'ont donc **ni la même
espérance de base, ni le même profil de perte**. Retourner les signes
d'une règle validée à l'achat ne produit pas une règle validée à la
vente. C'est précisément ce que ce document refuse de faire.

---

## ÉTAPE 1 — L'hypothèse économique

### 1. Quel comportement exploite-t-on ?

Après une **mauvaise** surprise trimestrielle, le cours d'un titre
continue de dériver à la baisse pendant plusieurs semaines, au lieu de
s'ajuster d'un coup le jour de l'annonce.

C'est la face négative de la dérive post-annonce — le même phénomène
que l'hypothèse n°2, du côté des mauvaises nouvelles.

### 2. Qui est de l'autre côté, et pourquoi accepte-t-il de perdre ?

Trois populations, et aucune n'est irrationnelle :

**Les détenteurs qui n'ont pas encore vendu.** Vendre à perte demande
d'admettre une erreur. L'effet de disposition — garder ses perdants,
couper ses gagnants — est l'un des biais les mieux documentés en
finance comportementale. Ces vendeurs arrivent, mais étalés.

**Les gérants contraints par leur mandat.** Un fonds qui doit sortir
d'un titre dégradé le fait progressivement, pour ne pas peser sur le
cours. Cette sortie s'étale mécaniquement sur des semaines.

**Ceux qui ne peuvent pas vendre à découvert.** La majorité des
investisseurs particuliers et beaucoup de fonds n'y sont pas autorisés.
Face à une mauvaise nouvelle, leur seule action possible est de ne pas
acheter. L'information négative s'incorpore donc **plus lentement** que
l'information positive.

### 3. Pourquoi l'effet n'a-t-il pas disparu ?

**Et c'est ici que se joue tout le test.**

La raison même pour laquelle l'effet pourrait survivre — vendre à
découvert est coûteux et contraint — est la raison pour laquelle il
pourrait être **incapturable**. Si l'arbitrage était gratuit, l'effet
serait arbitré ; s'il ne l'est pas, c'est que son coût mange le gain.

Le test doit donc être **brutal sur les coûts**. Une hypothèse qui ne
survit qu'à frais nuls n'est pas une hypothèse, c'est une illusion
d'optique comptable. L'étape 6 n'est pas une formalité : c'est le
cœur du sujet.

---

## ÉTAPE 2 — Les règles, gelées

### Mesure de la surprise

Identique à l'hypothèse n°2, pour que les deux faces soient
comparables :

> **CAR3** = rendement du titre moins rendement de l'indice, cumulé sur
> les 3 séances allant de la veille de l'annonce au lendemain
> (J−1, J, J+1).

### Conditions d'entrée

Toutes vraies, évaluées à la **clôture de J+2**, exécution à
**l'ouverture de J+3** :

| # | Condition | Seuil |
|---|---|---|
| E1 | CAR3 | **≤ −5,0 %** |
| E2 | Volume du jour d'annonce / moyenne 20 j | **≥ 2,0** |
| E3 | Clôture de J+1 | **en-dessous** de la clôture de J−1 |
| E4 | Prix | **≥ 10 €/$** |
| E5 | Volume en devise sur 20 j | **≥ 50 M** |
| E6 | Le titre | **sous sa SMA200** |

E1 et E2 définissent la mauvaise surprise. E3 écarte les cas où le
marché s'est ravisé dès le lendemain.

**E5 est plus sévère que pour l'achat** — 50 M au lieu de 20 M. Ce
n'est pas un réglage de performance : la disponibilité du titre à
l'emprunt et le coût de cet emprunt dépendent directement de sa
liquidité. Un titre peu liquide est cher à emprunter, parfois
introuvable, et c'est exactement sur ces titres-là que le rappel de
prêt tombe au pire moment.

**E6 remplace le filtre d'indice de l'hypothèse n°2.** Exiger que
l'indice soit sous sa MM200 réduirait l'échantillon à presque rien sur
la période de validation. Exiger qu'il soit au-dessus n'aurait aucun
sens pour une vente. On retient donc un filtre **au niveau du titre**
— il est déjà en tendance baissière — et **aucun filtre d'indice**.

Ce choix est un degré de liberté, et il est déclaré ici, avant tout
test. Il sera éprouvé **une seule fois**, en robustesse, sous la forme
d'une variante avec filtre d'indice ; le verdict go/no-go se prononce
sur les règles gelées ci-dessus, pas sur la variante.

### Conditions de sortie

Dans l'ordre, la première atteinte rachète la position :

| # | Condition | Valeur |
|---|---|---|
| S1 | Durée maximale | **45 séances** |
| S2 | Stop sur clôture | **entrée + 2,0 × ATR(14)** |
| S3 | Annonce suivante | rachat la **veille** |
| S4 | Thèse morte | clôture **au-dessus de la SMA200** |

**Aucun take-profit**, même raison qu'à l'hypothèse n°2 : couper la
dérive là où elle produit son rendement est l'erreur qu'on ne refait
pas.

**Le stop est sur clôture, et il ne protège pas d'un écart
d'ouverture.** C'est assumé et c'est le risque principal : une offre
de rachat ou un résultat inversé peut ouvrir 40 % plus haut. Le stop
sort alors au cours réel d'ouverture, pas au niveau souhaité.

### Dimensionnement

| Paramètre | Valeur | Différence avec l'achat |
|---|---|---|
| Risque par position | **1 %** du sleeve | identique |
| Positions simultanées | **10** au maximum | identique à l'hypothèse n°2 |
| Poids maximum par ligne | **20 %** du sleeve | 25 % à l'achat |
| Vérification du poids | **à chaque séance** | à l'entrée seulement à l'achat |

Le poids se vérifie en continu parce qu'une vente à découvert perdante
grossit toute seule. Une ligne entrée à 10 % du sleeve qui double
représente 20 % d'exposition sans qu'aucun ordre n'ait été passé.

---

## ÉTAPE 3 — Les coûts propres à la vente à découvert

Ils ne sont pas un détail d'exécution. Ils sont l'hypothèse elle-même.

| Coût | Hypothèse retenue | Justification |
|---|---|---|
| Emprunt des titres | **2,0 % par an**, au prorata temporis | ordre de grandeur sur des valeurs liquides ; E5 à 50 M sert précisément à rester dans ce régime |
| Spread + commission | **0,10 % par côté** | identique à l'achat |
| Slippage | **0,05 % par côté** | identique à l'achat |
| Dividende dû au prêteur | **NON MODÉLISÉ** | voir ci-dessous |

### Ce que le test surestimera, et de combien

**Le dividende.** Le vendeur à découvert doit au prêteur tout dividende
détaché pendant la durée du prêt. Les données de cours utilisées ici ne
permettent pas de le reconstituer titre par titre de façon fiable.

Sur une détention de 45 séances, soit environ un cinquième d'année, un
titre au rendement de 2 % coûte environ **0,4 % de dividende**. Le
résultat du test est donc **optimiste d'environ 0,3 à 0,4 point par
trade** sur les titres distributeurs.

Ce chiffre n'est pas une estimation confortable : il s'ajoute
directement aux coûts et doit être retranché mentalement de
l'espérance affichée. Si l'avantage mesuré est inférieur à 0,4 point
par trade, **il n'existe pas.**

**Le rappel de prêt.** Un prêteur peut réclamer ses titres à tout
moment, forçant un rachat au pire moment. Non modélisé, non
modélisable avec ces données, et toujours défavorable.

---

## ÉTAPE 4 — Séparation des données

| Période | Rôle | Regards autorisés |
|---|---|---|
| 2010 – 2023 | Vérification technique du code | illimités |
| 2024 – 2026 | **Validation** | **un seul** |

La période de validation est celle de l'hypothèse n°2, qui n'a pas
encore été consommée. Elle n'a jamais servi à régler quoi que ce soit.

---

## ÉTAPE 5 — Les cinq critères

Les cinq doivent passer. Un seul échec vaut NO-GO.

| # | Critère | Seuil |
|---|---|---|
| 1 | Nombre de trades hors échantillon | **≥ 200** |
| 2 | Profit factor | **≥ 1,15** |
| 3 | Espérance après tous les coûts | **> 0** |
| 4 | z contre annonces neutres | **≥ 2** |
| 5 | Drawdown maximum | **< 20 %** |

### Le contrôle par le hasard, adapté

Le témoin n'est **pas** une date au hasard. C'est une **autre
annonce**, sans surprise notable, vendue à découvert selon les mêmes
règles.

Sinon on comparerait « vendre après une mauvaise surprise » à « vendre
n'importe quand », ce qui mélangerait l'effet cherché avec le simple
fait de vendre à découvert un marché qui monte.

---

## ÉTAPE 6 — Sensibilité aux coûts, obligatoire

Quatre hypothèses, affichées côte à côte :

| Hypothèse | Emprunt | Spread + slippage |
|---|---|---|
| Sans aucun frais | 0 % | 0 % |
| Emprunt seul | 2 % / an | 0 % |
| Réaliste | 2 % / an | 0,15 % par côté |
| Titre difficile à emprunter | **10 % / an** | 0,30 % par côté |

**La dernière ligne décide.** Si l'avantage disparaît à 10 % d'emprunt
annuel, l'hypothèse ne tient que sur des titres faciles à emprunter —
et ce sont rarement ceux qui baissent.

---

## ÉTAPE 7 — La barre économique

Battre les cinq critères ne suffit pas. La stratégie doit ensuite
battre **ne rien faire**, net de PFU à 30 % et de frais de rotation.

Une position vendeuse ne bénéficie d'aucun abattement pour durée de
détention et ne peut loger dans un PEA. Elle se compare donc au
compte-titres ordinaire, au taux plein.

---

## ÉTAPE 8 — Ce qui se passe après le résultat

**Si GO** : la stratégie entre en observation papier pendant six mois
avant tout ordre réel. Aucune exception. Le risque de perte non bornée
impose cette étape que l'achat ne justifiait pas.

**Si NO-GO** : l'hypothèse est morte. Elle ne se retouche pas, ne se
re-teste pas avec des seuils ajustés, et ne revient pas sous un autre
nom. On inscrit le résultat au registre et on passe à autre chose.

**Si l'échantillon est insuffisant** (moins de 200 trades avec z
positif) : on peut élargir l'univers de titres, **sans toucher à une
seule règle**. C'est la seule extension autorisée.

---

## À inscrire au registre AVANT de lancer

- Hypothèse n°3, dérive post-annonce négative, vente à découvert
- Spécification v1.0, figée à la rédaction
- Période de validation : 2024-01-01 → 2026-12-31, **un seul passage**
- Biais connu et accepté : dividende dû au prêteur non modélisé,
  résultat optimiste d'environ 0,3 à 0,4 point par trade
- Biais connu et accepté : rappel de prêt non modélisé
- Degré de liberté déclaré : absence de filtre d'indice, éprouvée une
  fois en robustesse, sans effet sur le verdict
