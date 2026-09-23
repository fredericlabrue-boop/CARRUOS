# DÉRIVE POST-ANNONCE v1.0 — NOTE DE LECTURE
### Rédigée le 23 septembre 2026, **avant** tout regard sur la période de validation
### Ne change aucune constante. L'empreinte des constantes reste celle du registre.

---

## Pourquoi cette note existe

La spécification `derive-post-annonce-v1.md` est gelée : son texte ne
bouge pas, son empreinte SHA256 est vérifiée à chaque passage des tests.
Mais un texte se lit, et un moteur est une lecture. En relisant `pead.py`
ligne à ligne avant le passage unique, j'ai trouvé des endroits où le
moteur ne faisait pas ce que le texte dit — et un endroit où le texte
lui-même doit être lu, parce qu'il ne dit pas tout.

Chaque lecture est écrite ici **avant** que quiconque ait vu un résultat
sur 2024–2026. Aucune n'a été choisie en regardant un chiffre. Cette
note a sa propre empreinte, vérifiée par `test_moteur` comme celle de la
spécification, et le registre inscrit l'empreinte du code qui a tourné.

---

## 1. Le « jour d'annonce » est la première séance qui peut y réagir

**Ce que faisait le moteur.** Il prenait la date du calendrier. Pour une
société qui publie après la clôture — c'est le cas de la plupart des
grandes valeurs américaines — le jour J était donc une séance où
personne ne connaissait encore les chiffres. Conséquences :

- **E2** mesurait le volume d'une séance ordinaire : le volume de la
  réaction tombait le lendemain. Une publication après la clôture ne
  passait E2 que par accident ;
- **E3** comparait la clôture de la réaction à celle de l'avant-veille :
  il ne vérifiait plus du tout que « le marché ne s'est pas ravisé dès
  le lendemain », qui est sa raison d'être écrite.

**La lecture retenue.** J est la première séance dont les échanges
peuvent refléter la publication :

| Heure de la publication (New York) | J |
|---|---|
| à partir de 16 h (après la clôture) | la séance **suivante** |
| avant 16 h (avant l'ouverture ou pendant la séance) | le jour même |
| jour sans séance (week-end, férié) | la séance suivante |
| heure inconnue | le jour du calendrier — la lecture littérale, **comptée à part** dans le rapport |

**Pourquoi c'est une lecture et non un changement.** La spécification
définit CAR3 comme « la mesure standard », et la convention standard
des études d'événement place le jour 0 d'une publication après la
clôture à la séance suivante. E3 n'a de sens qu'ainsi. Et E1 et E2
« définissent la surprise » : le volume qui compte est celui de la
réaction. 16 h est l'heure de clôture de New York, un fait de marché,
pas un réglage.

**Ce que je n'ai pas fait.** Choisir J en regardant où le volume saute.
La spécification l'interdit (étape 4, voie C), et elle a raison : ce
serait trier les événements dans le sens de l'effet cherché.

## 2. E6 est évalué à la clôture de J+2

« Toutes vraies, évaluées à la clôture de J+2. » Le moteur évaluait le
régime de l'indice à J. Corrigé, pour l'entrée comme pour le choix des
annonces témoins.

## 3. S3 sort à la clôture de la veille, pas de l'avant-veille

« Sortie la veille » de l'annonce suivante : à la clôture de la
dernière séance strictement avant sa date. Le moteur sortait une séance
plus tôt, par un décalage d'indice. La date prise en compte est celle
du calendrier de l'annonce suivante, quelle que soit son heure : sortir
la veille est sûr dans tous les cas.

## 4. Une position encore ouverte à la fin des données n'est pas un trade

Le moteur fermait au dernier cours connu toute position que les données
laissaient ouverte, en inscrivant « durée » ou « annonce » comme motif —
comme si une règle avait joué. Ces positions sont maintenant **exclues**
des mesures et **dénombrées** dans le rapport. Même traitement pour les
annonces témoins.

## 5. La table des coûts a quatre lignes, et la dernière est éliminatoire

L'étape 6 en demande quatre ; le moteur en affichait trois, sans la
ligne « clôture du jour, sans frais ». Les quatre :

| Ligne | Entrée | Frais par côté |
|---|---|---|
| 1 | clôture de J+2 | aucun — plafond irréaliste |
| 2 | ouverture de J+3 | aucun |
| 3 | ouverture de J+3 | 0,15 % — **les cinq critères se mesurent ici** |
| 4 | ouverture de J+3 | 0,30 % |

« Si l'avantage ne survit pas à la dernière ligne, il n'existe pas. »
Lu ainsi : un GO exige en plus une **espérance strictement positive à
la ligne 4**. Cette règle ne peut que rejeter davantage — impossible à
jouer dans le bon sens.

## 6. Le témoin du critère 4

Les annonces **sans surprise** (E1 échoue) qui passent E4 et E6, du
même univers et de la même période. Chacune est rejouée avec
exactement les mêmes règles de sortie que les vrais trades. On tire au
hasard, avec remise, autant d'annonces témoins qu'il y a de trades, on
en prend le rendement moyen ; 1 000 tirages, graine 7. z = (rendement
moyen réel − moyenne des tirages) / écart-type des tirages. Moins de
20 annonces témoins simulables : pas de z, et le critère échoue en le
disant.

## 7. Conventions reprises du moteur de la stratégie 1

- **Le stop sur clôture s'exécute à cette clôture.** C'est la
  convention du moteur de la stratégie 1, gardée pour que les deux
  résultats se comparent. Elle est **optimiste** : en pratique on
  connaît la clôture une fois qu'elle est faite. La ligne 4 de la table
  des coûts en couvre une partie, pas tout.
- La moyenne de volume sur 20 séances **inclut** la séance de réaction.
  Lecture conservatrice : elle abaisse légèrement le rapport E2.

## 8. Les données, figées avant le passage

- Univers : S&P 500 + Nasdaq 100, la composition **du jour de la
  préparation**. Le biais du survivant est affiché en tête du rapport.
- Les dates d'annonces sont relevées une fois, rangées dans un
  instantané daté, et le passage unique lit cet instantané — pas Yahoo
  le jour même. L'empreinte de l'instantané est inscrite au registre.
- 2022–2023 fait partie de la période de validation de la
  spécification mais n'est pas utilisé par la voie A (2024–2026, dans
  les constantes gelées). Ces deux années restent **vierges**.

## 9. Ce qui s'affiche

Le taux de réussite ne s'affiche jamais seul : toujours avec son
nombre de trades et son intervalle de Wilson, comme partout ailleurs
dans le programme.

## 10. Le passage ne part pas sur des données incomplètes

Un passage brûlé sur un univers tronqué serait perdu pour de bon. Il
refuse donc de partir, sans rien inscrire, si l'univers compte moins de
**450** titres (la liste du S&P 500 n'a pas pu être lue), si Yahoo n'a
rendu les dates que de moins de **90 %** des titres, si moins de
**80 %** des titres sont exploitables, ou si l'heure n'est connue que
pour moins de **50 %** des publications — sans l'heure, la lecture du
point 1 retombe sur la lecture littérale, c'est-à-dire sur le défaut
qu'elle corrige. Ces seuils regardent la complétude des données, jamais
un rendement.

## 11. Ce que la préparation montre de 2024–2026

Des **comptes**, aucun rendement : le nombre de publications, leur
répartition par heure, et le nombre de trades que les six conditions
donneront au plus. C'est ce qui dit à l'avance si le critère 1
(200 trades) est atteignable. La préparation ne rejoue aucune sortie
sur cette période.

---

*Une lecture écrite après le résultat serait une retouche. Celle-ci est
écrite avant, datée, et hachée — c'est ce qui la rend vérifiable.*
