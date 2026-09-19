# CARRUOS

Scanner d'actions personnel. Python, interface HTML servie en local et
affichée dans une fenêtre Windows.

---

## Installation, une seule fois

1. **Python 3.11 ou plus**, depuis [python.org](https://www.python.org/downloads/).
   Cocher **« Add python.exe to PATH »** pendant l'installation — sans
   cette case, rien ne démarrera.
2. Décompresser cette archive où vous voulez (Documents, un disque
   externe, peu importe).
3. Double-cliquer **`Carruos.bat`**, choisir **2. Installer**.
4. Choisir **9. Tests du système**. Les trois doivent passer.
5. Choisir **1. Lancer Carruos**.

`3. Créer le raccourci` pose un lanceur sur le Bureau.
`4. Préparer une clé USB` emporte le tout, dépendances comprises.

---

## Le menu

| | |
|---|---|
| **1** | lancer l'application |
| **2** | installer ou mettre à jour les dépendances |
| **5 / 6** | Phase 0 — go/no-go, S&P 500 ou 120 titres US |
| **P** | dérive post-annonce (hypothèse 2) |
| **S** | dérive post-annonce **négative**, vente à découvert (hypothèse 3) |
| **Q** | pourquoi un titre est-il refusé ? |
| **J** | journal d'audit des signaux |
| **F** | figer la composition d'un univers |
| **C** | état du cache des cours |
| **R** | épreuves de robustesse sur un rapport déjà calculé |
| **Z** | calibrer le critère 4 sur des cours aléatoires |
| **H** | amplitude par horizon et take-profit envisageable |
| **7 / 8 / G** | portefeuille IBKR, **lecture seule** |
| **9** | les trois tests |

---

## À faire chaque trimestre : `F`

Le backtest teste le passé avec la composition **d'aujourd'hui** du
S&P 500. C'est le biais du survivant : les faillites et les retraits de
cote ont été retirés de l'échantillon après coup, donc le backtest ne
peut pas perdre dessus et son résultat est flatté.

Personne ne peut remonter le temps. On peut arrêter d'en perdre :
`F` enregistre la composition du jour, datée. Dans trois ans, ces
fichiers seront l'historique qui manque aujourd'hui. Tant qu'aucune
composition d'époque ne couvre la période testée, la Phase 0 écrit
l'avertissement en tête de son rapport.

---

## Ce qui est mesuré, ce qui ne l'est pas

Le programme refuse par construction d'afficher :

- un pourcentage unique de « chances de gagner » — toujours l'intervalle
  de Wilson **avec** le nombre de trades ;
- un score composite bâti sur des poids non testés ;
- un verdict directionnel (HAUSSIER, ACHAT) dérivé d'un tel score ;
- une ligne de prédiction de prix. Le cône de dispersion a sa dérive
  fixée à zéro : il donne l'amplitude, jamais le sens.

**Le plafond de poids par ligne est appliqué au backtest**, pas seulement
au scan du jour. Il ne l'était pas : le backtest dimensionnait au seul
risque, si bien qu'un stop très serré produisait une position à 200 % du
capital. Sur données d'essai, un quart des lignes dépassaient le plafond
de 25 %. Le rapport dit désormais combien de lignes ont été réduites et
quel poids a réellement été atteint.

**Les paramètres de stratégie sont gelés**, et la règle est exécutable.
Chaque hypothèse a sa propre empreinte SHA256 — trois empreintes
séparées, pour qu'on sache **laquelle** a bougé — et `test_moteur` tombe
si l'une d'elles change, ou si l'un des trois documents de spécification
a été retouché. Un résultat ne peut plus être attribué par erreur à un
jeu de paramètres qui ne l'a pas produit.

    py -m equity_scanner.audit --parametres

**État de la validation.**

| | hypothèse | état |
|---|---|---|
| 1 | repli en tendance | **NO-GO**. Morte, ne se retouche pas. |
| 2 | dérive post-annonce | moteur codé, test pas encore lancé |
| 3 | dérive post-annonce **négative** (short) | moteur codé, test pas encore lancé |

L'hypothèse 3 n'est pas l'hypothèse 2 avec les signes inversés. Vendre à
découvert a ses propres asymétries : la perte n'est pas bornée, la
position **grossit** quand elle a tort, emprunter les titres se paie, et
le marché dérive à la hausse — il ne suffit pas d'avoir raison, il faut
avoir assez raison pour couvrir cette dérive.

Et le test la flatte sur un point, qu'il faut retrancher à la main : le
**dividende dû au prêteur n'est pas modélisé**, faute de données titre
par titre. Sur 45 séances, cela représente environ **0,4 point par
trade**. Si l'espérance mesurée est inférieure à 0,4 point, l'avantage
n'existe pas.

---

## Quand un titre disparaît d'un scan

Il ressort toujours avec son motif : série trouée, division non ajustée,
cotation figée, volume nul, données périmées, décrochage du calendrier
de l'indice. Le principe est de **refuser de conclure** plutôt que de
compléter une barre manquante en silence — une barre inventée fausse le
RVOL, l'ATR et le RSI de la séance, et le signal qui en sort a l'air
parfaitement normal.

Pour savoir précisément ce qui bloque : menu **Q**, ou

```
py -m equity_scanner.qualite AAPL MC.PA
```

---

## La clé Alpha Vantage

Elle est **à toi** : gratuite en trente secondes sur
[alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key).
Elle n'est écrite nulle part dans le programme, et elle ne doit pas
l'être — un fichier partagé ou copié sur une clé USB l'emmènerait avec
lui.

Colle-la dans le champ **CLE ALPHA VANTAGE** de la page d'accueil. Elle
est alors enregistrée **à deux endroits** :

- `.bruce_cache\cle-alphavantage.txt`, à côté du programme ;
- `%USERPROFILE%\.carruos\cle-alphavantage.txt`, dans ton dossier
  personnel.

C'est la seconde copie qui compte. `.bruce_cache` est créé à l'usage et
ne fait pas partie de l'archive : installer une nouvelle version dans un
dossier neuf faisait disparaître la clé sans un mot, et les actualités
tombaient en panne sans explication. Elle est maintenant retrouvée toute
seule.

Pour l'effacer : vide le champ et enregistre — elle part des deux
endroits à la fois.

---

## Si quelque chose ne va pas

| Symptôme | Cause la plus fréquente |
|---|---|
| « Python introuvable » | case *Add python.exe to PATH* oubliée ; réinstaller |
| l'appli s'ouvre dans le navigateur | `pywebview` absent ; menu **2** |
| un scan ne rend aucun candidat | marché sous sa MM200 : c'est la règle, pas une panne |
| le micro du majordome ne marche pas | normal dans la fenêtre Windows — voir ci-dessous |
| tous les titres sont refusés | menu **Q** sur l'un d'eux : le motif est écrit |
| un scan semble lent la première fois | premier passage = téléchargement ; les suivants relisent le cache |
| `test_moteur` échoue sur l'empreinte | un paramètre gelé a bougé. Ce n'est pas le test qu'il faut corriger |

Le cache des cours, la clé Alpha Vantage, les positions et le journal
d'audit vivent dans `.bruce_cache`, à côté du programme. Supprimer ce
dossier remet tout à zéro sans rien casser.

---

## Comprendre la page d'accueil

**La case PHASE 0** en bas du bandeau affiche le nombre de rapports
posés à côté du programme. **Cliquez dessus** : elle explique ce qu'est
un rapport de Phase 0, liste ceux que vous avez (nombre de trades,
période, espérance, profit factor) et rappelle le verdict connu.

Un rapport de Phase 0 est le résultat d'un **rejeu des règles sur
l'historique** : chaque trade que le système aurait pris, avec son
entrée, sa sortie, son stop et son résultat. Il répond à une seule
question — le signal fait-il mieux que le hasard ? **Ce n'est pas une
liste d'actions à acheter.**

**Le rail MES LIGNES À TRAITER**, sous le titre CARRUOS, ne compte
**pas** des titres à acheter. Il compte **vos propres positions** — celles
que vous avez saisies dans le bloc du bas — dont au moins une des quatre
conditions de sortie de la spécification est active, ou dont le stop que
vous avez noté est dépassé. Le chiffre est à zéro quand toutes vos lignes
sont à CONSERVER. **Cliquez dessus** : il nomme chaque ligne concernée et
dit **quelle** condition est active, jamais « vends ».

L'ancien libellé était « À SURVEILLER », et il se lisait comme une liste
d'achats. Il ne l'a jamais été.

**Les actions à surveiller**, après un scan, sont les titres qui
remplissent une partie des treize blocs d'entrée, pas tous. La colonne
de droite dit lesquels manquent. **Cliquez sur le nom** : une fiche
s'ouvre avec le motif de la surveillance, puis tous les faits mesurés —
le plus haut de la période, le recul depuis ce sommet, les écarts aux
moyennes, le RSI, et l'état des quatre conditions de sortie. Le
graphique complet reste à un bouton de là. Échap referme.

---

## L'onglet STRATÉGIE

Bouton **STRATEGIE** en haut de l'accueil. Deux moitiés, de nature très
différente — et c'est important.

**À gauche, de l'arithmétique.** Le même rendement traité de trois
façons : un ETF capitalisant (impôt seulement à la revente), une
rotation active (PFU chaque année plus les frais), et des gains retirés
au fil de l'eau. Le rendement que vous saisissez est **votre
hypothèse** : la page en tire les conséquences, elle ne les devine pas.
Elle affiche aussi la *barre à franchir* — le rendement brut qu'une
rotation doit produire pour seulement **égaler** un capitalisant, une
fois l'impôt annuel et les frais comptés. Bascule compte-titres (30 %)
ou PEA de plus de cinq ans (17,2 %).

**À droite, des faits.** Pour **chaque ligne de votre registre** — pas
une seule, toutes : le plus haut atteint depuis l'entrée et sa date, le
recul depuis ce sommet, la part du gain maximum rendue, les écarts aux
moyennes en ATR, la marge avant le stop, la date de publication des
résultats, et ce que coûterait fiscalement une vente aujourd'hui.

Le champ du haut examine **n'importe quel titre**, détenu ou non. Sans
position, vous obtenez ce qui ne dépend pas d'elle : le plus haut de la
période, le recul depuis ce sommet et depuis le plus haut de 52
semaines, les écarts aux moyennes, les conditions de sortie. Aucun prix
d'entrée n'est inventé pour combler le trou — donnez-en un et le trajet
complet apparaît.

Puis l'état des **quatre conditions de sortie de votre spécification** —
actives ou dormantes. C'est votre plan qui parle, pas un score.

**Aucun verdict n'est calculé.** Pas de « garder » ni de « vendre », pas
de score composite, pas de chiffrage du géopolitique. Une information
publique est déjà dans les cours ; les actualités sont du contexte pour
votre vérification avant de passer l'ordre, jamais un signal.

---

## Changer de thème

Roue dentée en haut à droite, section **THÈME**. Trois ambiances, qui
s'appliquent immédiatement et sont reprises au lancement suivant :

| | |
|---|---|
| **CARRUOS** | cyan et or, sobre — l'original |
| **JARVIS** | hologramme bleu clair et or, lumineux |
| **ULTRON** | très sombre, néons violet et rouge |
| **RÉACTEUR** | bleu électrique dense, tableau de bord instrumenté |

Le thème repeint tout : fond, panneaux, jauges, radar, hologramme. La
palette d'accent, juste en dessous, ne change ensuite que la couleur
d'accent si vous voulez affiner.

---

## Le majordome et le micro

**Le micro ne peut pas fonctionner dans la fenêtre Windows.** Ce n'est pas
un réglage à trouver : cette fenêtre s'appuie sur le moteur WebView2, qui
n'embarque pas le service de transcription de Chrome. La brique est
absente, pas mal configurée.

Deux chemins, tous deux pleinement fonctionnels :

- **Écrire.** Le champ de saisie du panneau fait exactement le même
  travail, et le majordome répond à voix haute comme à l'oral.
  `analyse sanofi` · `scan cac 40` · `état du marché` · `mes positions`
  · `actualise`
- **Le bouton EDGE.** Il ouvre la même page dans votre navigateur par
  défaut, où le micro fonctionne réellement.

Le panneau se ferme par **la croix**, par **Échap**, ou en recliquant sur
le disque du majordome.

---

## Pour les curieux : la ligne de commande

```
py -m equity_scanner.app                       l'application
py -m equity_scanner.scan --tickers AMD,MU --sleeve 8000
py -m equity_scanner.phase0 --univers sp500 --csv rapport.csv
py -m equity_scanner.qualite AAPL              contrôle qualité
py -m equity_scanner.audit --parametres        paramètres gelés + empreinte
py -m equity_scanner.robuste --csv rapport.csv stabilité, Monte Carlo
py -m equity_scanner.cache --etat              taille du cache
py -m equity_scanner.data --figer sp500        composition datée
```

`--fils N` règle le nombre de téléchargements simultanés (8 par défaut,
16 au maximum : au-delà, Yahoo limite le débit).

À lancer **après la clôture US** (22h ou 23h heure de Paris). Toutes les
règles sont évaluées sur clôture ; un scan en séance produit des signaux
qui n'existeront plus le soir.
