# DÉRIVE POST-ANNONCE NÉGATIVE v1.0 — NOTE DE LECTURE
### Rédigée le 30 septembre 2026, **avant** tout regard de l'hypothèse n°3 sur sa période de validation
### Ne change aucune constante. L'empreinte des constantes reste `47d593c5…`.
### Point 11 revu le même jour, **avant** la validation du propriétaire et avant tout regard : le rachat du stop suit le mot « ouverture » du texte.

---

## Pourquoi cette note existe

La spécification `strategie-short-v1.md` est gelée depuis le
18 septembre 2026 : son texte ne bouge pas, son empreinte SHA256 est
vérifiée à chaque passage des tests. Mais un moteur est une lecture du
texte, et celle de `short.py` avait les défauts que la note de lecture
de l'hypothèse n°2 a corrigés le 23 septembre — plus quelques-uns qui lui
sont propres. Cette note les écrit **avant** que le moteur ait calculé le
moindre rendement sur 2024–2026, les date, et les hache. Aucune lecture
n'a été choisie en regardant un chiffre de l'hypothèse n°3.

Quand le texte laisse deux lectures, celle retenue est celle qui **ne
peut que rejeter davantage** : une règle écrite avant le test et qui
durcit ne se joue pas dans le bon sens.

---

## 1. Le « jour d'annonce » est la première séance qui peut y réagir

**Ce que faisait le moteur.** Il prenait la date du calendrier, sans
l'heure. Pire qu'à l'hypothèse n°2 : une annonce tombée un jour sans
séance était rattachée à la séance **précédente** — une séance où
personne ne pouvait encore la connaître.

**La lecture retenue** est celle de l'hypothèse n°2, pour que les deux
faces se comparent — la spécification le demande (« identique à
l'hypothèse n°2 ») :

| Heure de la publication (New York) | J |
|---|---|
| à partir de 16 h (après la clôture) | la séance **suivante** |
| avant 16 h | le jour même |
| jour sans séance | la séance **suivante** |
| heure inconnue | le jour du calendrier — lecture littérale, **comptée à part** dans le rapport |

E2 mesure alors le volume de la séance qui réagit, et E3 compare la
clôture de J+1 à celle de J−1 autour de la vraie réaction.

## 2. E4, E5 et E6 sont évalués à la clôture de J+2

« Toutes vraies, évaluées à la clôture de J+2. » Le moteur le faisait
déjà ; c'est écrit ici pour que ça ne bouge plus.

## 3. S3 rachète à la clôture de la veille, pas de l'avant-veille

« Rachat la veille » de l'annonce suivante : à la clôture de la dernière
séance **strictement avant** sa date du calendrier. Le moteur rachetait
une séance plus tôt, par un décalage d'indice. Et l'annonce suivante se
lit dans la **liste complète** des publications du titre : le moteur la
prenait dans la liste des événements retenus, d'où il manquait les
annonces trop proches des bords des données.

## 4. Une position encore ouverte à la fin des données n'est pas un trade

Le moteur la rachetait au dernier cours connu en inscrivant « durée » ou
« annonce » comme motif — comme si une règle avait joué. Elle est
maintenant **exclue** des mesures et **dénombrée** dans le rapport. Même
traitement pour les annonces témoins.

## 5. Les cinq critères se mesurent à la ligne « réaliste », et la dernière ligne décide

L'étape 3 fixe les coûts retenus : emprunt 2 % par an au prorata,
0,10 % + 0,05 % par côté. C'est la ligne 3 de l'étape 6, et les cinq
critères s'y mesurent.

« **La dernière ligne décide.** » Le moteur l'affichait sans s'en
servir. Lu ainsi : un GO exige en plus une **espérance strictement
positive** à la ligne « difficile à emprunter » (10 % par an, 0,30 %
par côté).

## 6. Le dividende non modélisé est une condition, pas une remarque

« Si l'avantage mesuré est inférieur à 0,4 point par trade, **il
n'existe pas**. » Le moteur laissait cette soustraction au lecteur. Lu
ainsi : un GO exige un **rendement moyen par trade d'au moins
0,4 point** à la ligne « réaliste ». Le rappel du dividende reste
affiché à chaque rapport, qu'il passe ou non.

## 7. Le témoin du critère 4

« Une **autre annonce**, sans surprise notable, vendue à découvert selon
les mêmes règles. »

- **Sans surprise notable** : |CAR3| < 5 %. Ni mauvaise surprise, ni
  bonne. Le moteur prenait toute annonce qui ne passait pas E1, bonnes
  surprises comprises. Or vendre après une bonne surprise perd si la
  dérive positive existe : le témoin aurait été plus facile à battre.
  La lecture littérale est aussi la plus sévère.
- **Selon les mêmes règles** : le témoin passe E4, E5 et E6 — tout ce qui
  ne définit pas la surprise. Le texte dit que « E1 et E2 définissent la
  mauvaise surprise » et que E3 écarte le marché qui se ravise ; E5, lui,
  est une condition d'**empruntabilité**, que tout titre vendu à
  découvert doit remplir.
- Chaque témoin est rejoué **une fois** avec les mêmes sorties et les
  mêmes coûts, puis on tire au hasard, avec remise, autant de témoins
  qu'il y a de trades ; 1 000 tirages, graine 7.
- Moins de **20** annonces témoins simulables : pas de z, et le critère
  échoue en le disant. Le moteur rendait z = 0 sans rien dire.

## 8. L'univers et l'indice

La spécification n'écrit pas l'univers — l'étape 2 du protocole
l'exige. Lu comme à l'hypothèse n°2, dont celle-ci est « la face
négative » : **S&P 500 + Nasdaq 100**, composition du jour de la
préparation, chargée composante par composante (`data.univers_detaille`,
arrêt si une composante manque sans repli daté). L'indice de CAR3 est
SPY. Les seuils E4 et E5 sont donc en **dollars**.

**Le biais du survivant n'a pas de sens connu pour une vente à
découvert.** À l'achat, il flatte : les sociétés disparues manquent. Ici
manquent à la fois celles qui ont fait faillite — qui auraient rapporté —
et celles qui ont été rachetées avec une prime — qui auraient coûté. Le
rapport le dit au lieu d'écrire « flatté ».

## 9. La variante de robustesse : l'indice SOUS sa MM200

« Il sera éprouvé une seule fois, en robustesse, sous la forme d'une
variante avec filtre d'indice ; le verdict go/no-go se prononce sur les
règles gelées. » Le texte ne dit pas quel filtre. Il dit qu'exiger
l'indice au-dessus « n'aurait aucun sens pour une vente » : la variante
est donc **SPY sous sa MM200 à la clôture de J+2**. Elle est calculée
**une fois**, au passage unique seulement, affichée à part, et n'entre
jamais dans le verdict.

## 10. La barre économique : battre « ne rien faire », net de PFU

Étape 7. Le capital du sleeve à la fin de la période, **après 30 % de PFU
sur le gain**, doit dépasser le capital de départ : rendement annualisé
net strictement positif. Les frais de rotation sont déjà dans les coûts.
Sinon : GO technique, NON économique, et rien ne se déploie.

Un GO complet n'est pas un feu vert : l'étape 8 impose **six mois
d'observation papier** avant tout ordre réel, et le rapport le dit.

## 11. Le rachat sur S2 et S4 : lu à la clôture, exécuté à l'ouverture

Le texte : « Le stop est sur clôture, et il ne protège pas d'un écart
d'ouverture. […] Le stop sort alors au **cours réel d'ouverture**, pas
au niveau souhaité. »

- **S2 (stop) et S4 (thèse morte) se lisent à la clôture et rachètent à
  l'ouverture de la séance suivante**, au cours réel. C'est la séparation
  que la spécification écrit déjà pour l'entrée — condition à la clôture
  de J+2, vente à l'ouverture de J+3 — et la seule lecture où le mot
  « ouverture » du texte a un sens. Un écart d'ouverture est compté en
  entier.
- Les moteurs des hypothèses n°1 et n°2 rachetaient **à la clôture même**
  qui déclenchait : une convention optimiste, puisqu'on ne connaît une
  clôture qu'une fois faite. Elle n'est pas reprise ici, parce que le
  texte de l'hypothèse n°3 dit « ouverture ». Les résultats des deux
  faces se comparent donc à cette différence près, et le rapport de
  l'hypothèse n°2 est archivé tel qu'il a tourné.
- **La première clôture surveillée est celle du jour de la vente**
  (J+3) : « dans l'ordre, la première atteinte rachète la position ».
  Les moteurs précédents ne regardaient qu'à partir du lendemain.
- **S1 et S3 sont connues d'avance** — la 45ᵉ séance, la veille de
  l'annonce suivante — et rachètent à la clôture de leur séance. Ce
  jour-là, elles passent avant un stop qui ne s'exécuterait que le
  lendemain.
- Un déclenchement sur la dernière séance des données n'a pas
  d'ouverture suivante : la position reste « ouverte » et n'est pas un
  trade (point 4).

## 12. Conventions reprises du moteur de l'hypothèse n°2

- La moyenne de volume sur 20 séances **inclut** la séance de réaction.
- Le plafond de 20 % par ligne est **mesuré** séance par séance et
  rapporté, pas corrigé : la spécification ne dit pas quel ordre passer
  quand il est franchi (chantier 5).
- Le taux de gagnants ne s'affiche qu'avec son nombre de trades et son
  intervalle de Wilson.

## 13. Les données, figées avant le passage

- **Les cours** couvrent la période de conception depuis son début,
  2010, préchauffage de 260 séances compris. Le moteur n'en chargeait que
  6 ans : la période de conception 2010–2023 n'était pas couverte du tout.
- Les dates d'annonces sont relevées une fois, rangées dans un
  instantané daté (`~/.carruos/strategie-3/annonces.json`), et le passage
  lit cet instantané. Son empreinte est inscrite au registre.
- Le passage **ne part pas** si l'univers compte moins de **450** titres,
  si les dates manquent pour plus de **10 %** des titres, si moins de
  **80 %** sont exploitables, ou si l'heure n'est connue que pour moins
  de **50 %** des publications. Ces seuils regardent la complétude des
  données, jamais un rendement.

## 14. Deux temps, comme à l'hypothèse n°2

- **La préparation**, répétable : relevé des dates, chargement, **des
  comptes sans aucun rendement** sur 2024–2026 (combien de trades au
  plus), puis une répétition générale sur **2010–2023**, dont le verdict
  est **indicatif** — seul le passage unique juge.
- **Le passage unique** : inscrit au registre **avant** le calcul, fermé
  **avant** l'affichage, refusé la seconde fois. Après une répétition
  NO-GO, il faut taper `LANCER QUAND MEME`.
- L'ancienne voie, qui calculait directement sur 2024–2026 sans rien
  inscrire, **n'existe plus**.

---

*Une lecture écrite après le résultat serait une retouche. Celle-ci est
écrite avant, datée, et hachée — c'est ce qui la rend vérifiable.*
