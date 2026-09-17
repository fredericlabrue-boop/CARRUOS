# PROTOCOLE DE VALIDATION
### La méthode avant l'idée — version 1.0, 14 septembre 2026

---

## Pourquoi ce document existe

Le 11 septembre, on a conçu « Repli en tendance ». Treize conditions,
paramètres figés à l'avance, quinze pages de spécification. L'idée
paraissait solide. Le 14 septembre, la Phase 0 a rendu NO-GO sur le
S&P 500 et sur les 120 titres US.

Ce n'est pas un échec de la stratégie. C'est le protocole qui a
fonctionné : il a coûté une nuit de calcul au lieu de plusieurs
milliers d'euros.

Ce document fixe la méthode pour les prochaines fois. Il se lit
**avant** d'avoir une idée, jamais après.

---

## La règle qui gouverne tout

> **Une hypothèse formulée après avoir vu les données n'est pas une
> hypothèse. C'est une description.**

Tout le reste découle de là.

Si tu regardes un graphique, que tu remarques un motif, et que tu
écris une règle qui capture ce motif, tu n'as rien découvert. Tu as
décrit ce que tu venais de voir. Le test qui suit ne teste rien.

---

## Le chiffre à garder en tête

Sept paramètres, cinq valeurs possibles chacun :

**5⁷ = 78 125 combinaisons.**

En cherchant dans cet espace, environ **3 900 combinaisons franchissent
z ≥ 2 par pur hasard**. Elles ne contiennent aucune information. Elles
existent parce que 78 125 tirages produisent mécaniquement des
extrêmes.

Une correction de Bonferroni exigerait z ≥ 4,9 pour un tel espace de
recherche — un seuil que presque aucune stratégie réelle n'atteint.

**Conséquence pratique : on ne cherche pas dans l'espace. On fixe un
point et on le teste.**

C'est la différence entre une expérience et une pêche.

---

## ÉTAPE 1 — L'hypothèse économique

Avant toute règle, trois questions par écrit. Si une seule reste sans
réponse, on s'arrête ici.

**1. Quel comportement humain ou contrainte structurelle exploite-t-on ?**

Un avantage vient toujours de quelque part. Un biais de comportement
(les gens vendent trop tôt les gagnants), une contrainte réglementaire
(les fonds doivent liquider avant la clôture annuelle), une friction
(un indice force des achats mécaniques à l'entrée d'un titre).

« Le RSI croise 40 » n'est pas une explication. C'est une observation.

**2. Qui est de l'autre côté, et pourquoi accepte-t-il de perdre ?**

À chaque fois que tu achètes, quelqu'un vend. S'il est mieux informé
que toi, plus rapide que toi, ou équipé de données que tu n'as pas,
c'est toi le pigeon.

Réponse acceptable : « un fonds indiciel contraint de vendre sans
considération de prix ». Réponse inacceptable : « quelqu'un qui n'a pas
vu le signal ».

**3. Pourquoi l'avantage n'a-t-il pas disparu ?**

Un avantage connu et facile à exploiter est arbitré en quelques mois.
S'il survit, c'est qu'il y a un coût, un risque, ou une contrainte qui
décourage les gros acteurs. Lequel ?

---

## ÉTAPE 2 — Le gel des règles

Les règles s'écrivent **en entier**, avant le premier test.

- Toutes les conditions d'entrée, chiffrées.
- Toutes les conditions de sortie, chiffrées.
- Le stop, le dimensionnement, les vetos.
- L'univers exact et la période exacte.
- Le créneau d'exécution.

Puis on horodate le fichier et on en calcule l'empreinte :

```
certutil -hashfile strategie-v1.md SHA256 > strategie-v1.sha256
```

Cette empreinte prouve que le fichier n'a pas bougé entre la
formulation et le résultat. Sans elle, rien ne t'empêche de te
convaincre après coup que « c'est ce qu'on avait prévu ».

**Aucune valeur ne change après cette étape.** Ni avant le test, ni
pendant, ni après.

---

## ÉTAPE 3 — La séparation des données

| Période | Rôle | Combien de fois on la regarde |
|---|---|---|
| 2010 – 2021 | Conception, vérification technique | autant qu'on veut |
| 2022 – 2026 | Validation | **une seule fois** |

La période de validation est un consommable. Une fois qu'on l'a
regardée, elle est brûlée pour cette hypothèse : tout ajustement
ultérieur testé dessus est contaminé.

Si tu as besoin d'un second essai, il faut une **nouvelle** période
non touchée, ou de nouveaux titres.

---

## ÉTAPE 4 — Le dimensionnement

Avant de lancer, on calcule combien de trades sont nécessaires pour que
le test ait une chance de détecter quelque chose.

Mesure faite sur le harnais actuel : **avec 170 trades, le test détecte
un avantage à partir d'environ 1,5 % par trade.** En dessous, il est
aveugle — l'absence de signal ne prouve rien.

Minimum retenu : **200 trades sur la période de validation.**

Ordre de grandeur observé : 30 titres produisent 77 trades sur
2022-2026. Il en faut donc **80 à 100 minimum**, davantage si la
stratégie est plus sélective.

Si l'univers disponible ne permet pas d'atteindre 200 trades,
**l'hypothèse n'est pas testable**. On ne la teste pas à moitié.

---

## ÉTAPE 5 — Les cinq critères

Tous doivent passer. Un seul manqué = NO-GO.

| # | Critère | Seuil | Ce qu'il écarte |
|---|---|---|---|
| 1 | Nombre de trades | ≥ 200 | un résultat porté par trois coups de chance |
| 2 | Profit factor | ≥ 1,15 | une rentabilité trop mince pour survivre aux frais |
| 3 | Espérance après coûts | > 0 | un système qui gagne brut et perd net |
| 4 | Score z vs entrées aléatoires | ≥ 2 | **le hasard** |
| 5 | Drawdown maximal | < 20 % | un système intenable à vivre |

### Le critère 4 est le seul qui compte vraiment

Mesure faite le 12 septembre sur des cours **purement aléatoires** :

- Profit factor : **1,48**
- Espérance : **positive**
- Score z : **+0,93** ← le seul qui rejette

Le système « gagnait de l'argent » sur du bruit pur. Les critères 2 et
3 étaient satisfaits. Seul le z a dit non.

**Ne jamais valider une stratégie sur le profit factor ou l'espérance.
Ce sont des chiffres qui mentent.**

---

## ÉTAPE 6 — Le contrôle par entrées aléatoires

Le principe : on remplace les signaux d'entrée par 1 000 tirages
aléatoires, on garde exactement les mêmes règles de sortie, le même
dimensionnement, le même univers et la même période.

On obtient une distribution de résultats dus au seul hasard. Le z
mesure de combien d'écarts-types la stratégie réelle dépasse cette
distribution.

C'est la seule mesure qui répond à la bonne question : **est-ce que le
choix du moment d'entrée apporte quelque chose, ou est-ce que n'importe
quelle entrée aurait fait pareil ?**

---

## ÉTAPE 7 — La robustesse

Chaque paramètre est décalé de ±20 %, un par un. On relance.

- Le résultat s'effondre → la stratégie tenait sur une valeur précise,
  c'est-à-dire sur de la chance. **NO-GO.**
- Le résultat se dégrade progressivement → comportement normal, c'est
  bon signe.

Attention : ce n'est **pas** une recherche du meilleur réglage. On ne
garde jamais la variante qui donne un meilleur chiffre. On vérifie
seulement que le résultat ne dépend pas d'un point exact.

---

## ÉTAPE 8 — La référence à battre

Le vrai concurrent n'est pas zéro. C'est **SMH acheté et conservé, net
de 30 % de PFU.**

Coût de la rotation, calculé le 11 septembre, à 15 %/an brut :

| Horizon | Rendement brut nécessaire pour **égaler** le buy & hold |
|---|---|
| 5 ans | 16,15 % |
| 10 ans | 17,30 % |

Plus environ 1 % par an de frais de courtage.

**Barre totale : battre le buy & hold de 2,5 à 3,5 points par an.**

Une stratégie qui passe les cinq critères mais ne franchit pas cette
barre est un GO technique et un NON économique. Elle ne se déploie pas.

---

## ÉTAPE 9 — La décision, et la fin de l'hypothèse

**GO** — les cinq critères passent et la barre économique est
franchie : déploiement sur le sleeve, plafonné à 25 % du portefeuille,
1 % de risque par trade, 5 positions maximum, circuit breaker à −6 %
par mois.

**NO-GO** — l'hypothèse est **morte**. Pas suspendue, pas à retoucher.
Morte.

### La règle la plus importante du document

> **Une hypothèse rejetée ne se modifie pas. Elle se remplace.**

Après un NO-GO, il est interdit de :

- changer un paramètre et relancer ;
- ajouter ou retirer une condition et relancer ;
- changer d'univers pour voir si « ça passe ailleurs » ;
- changer l'horizon de détention et relancer les mêmes indicateurs ;
- assouplir un seuil parce qu'on est passé « pas loin ».

Chacune de ces actions transforme le test en recherche. Et la
recherche, on l'a chiffrée plus haut : 3 900 faux positifs t'attendent.

**Une seule exception :** si le test a échoué sur le critère 1
(moins de 200 trades) avec un z positif, le test était
sous-dimensionné. On peut alors **élargir l'échantillon — titres ou
historique — sans toucher à une seule règle.** C'est la même hypothèse,
mieux mesurée.

---

## ÉTAPE 10 — Le registre

Un fichier unique, `registre-tests.md`, où **chaque test lancé** est
inscrit avant son résultat :

```
| date | hypothèse | empreinte SHA256 | univers | période | résultat | z |
```

On y inscrit les échecs. Surtout les échecs.

Sans ce registre, tu oublieras avoir testé quatre variantes et tu
croiras que la cinquième, qui passe, vaut quelque chose. Le registre
est ce qui rend le protocole honnête avec toi-même.

**Budget : trois hypothèses par an au maximum.** Au-delà, le nombre de
tests recrée le problème du grid search, à l'échelle de l'année.

---

## Les points de départ honnêtes

Si tu veux une hypothèse qui ne sort pas d'une intuition, voici des
effets documentés dans la littérature académique, mesurés sur
plusieurs décennies et plusieurs marchés. Ils ont au moins survécu à
un examen extérieur — ce qui ne garantit pas qu'ils survivent
aujourd'hui, ni après tes coûts.

**Momentum 12-1.** Acheter les titres les plus performants sur douze
mois en excluant le dernier mois, rééquilibrer mensuellement. Le plus
robuste des effets documentés, présent sur la plupart des marchés.
Faiblesse connue : effondrements brutaux aux retournements.

**Inversion à court terme.** Les titres les plus faibles d'une semaine
rebondissent la suivante. Horizon compatible avec ce que tu cherches.
Faiblesse connue : largement arbitré, et très sensible aux frais —
c'est précisément le terrain des fonds les plus rapides.

**Effet de faible volatilité.** Les titres les moins volatils
surperforment à risque ajusté. Horizon long, rotation lente, donc PFU
peu pénalisant.

**Dérive post-annonce de résultats.** Le prix continue de dériver dans
le sens de la surprise pendant plusieurs semaines après la publication.
Horizon de quelques semaines, compatible.

Chacun se formalise en quelques règles chiffrées, et passe par les dix
étapes ci-dessus. Sans exception.

---

## Résumé en une page

1. Pas d'idée sans explication économique ni réponse à « qui perd ? »
2. Règles écrites en entier, horodatées, empreinte calculée.
3. Période de validation touchée une seule fois.
4. 200 trades minimum, sinon non testable.
5. Cinq critères, tous obligatoires.
6. Le z est le seul juge — le profit factor ment.
7. Robustesse ±20 %, jamais pour optimiser.
8. Battre SMH de 2,5 à 3,5 points par an, net.
9. NO-GO = hypothèse morte, pas hypothèse à retoucher.
10. Tout est inscrit au registre, échecs compris.

---

*Le protocole ne sert pas à trouver une stratégie gagnante. Il sert à
ne pas déployer une stratégie perdante en croyant l'inverse. Ce sont
deux choses différentes, et seule la seconde est à ta portée.*
