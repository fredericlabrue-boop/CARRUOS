# CARRUOS — contexte pour Claude Code

Scanner d'actions personnel de Frédéric. Python, interface HTML servie en
local et affichée dans une fenêtre pywebview.

## Lancer

```
py -m equity_scanner.app          # l'application
py -m equity_scanner.test_pages   # contrôle des pages générées
py -m equity_scanner.test_rules   # contrôle des règles
py -m equity_scanner.test_moteur  # contrôle du moteur
```

**Les trois tests doivent passer avant tout commit.**

`test_moteur` vérifie en particulier que l'empreinte SHA256 des
paramètres gelés n'a pas bougé. S'il tombe sur cette ligne, ce n'est pas
le test qu'il faut mettre à jour : c'est le paramètre qu'il faut
remettre en place.

## Règle absolue du projet

Les paramètres de stratégie sont **gelés**. `PERIODES` dans
`indicators.py` (RSI 14, MACD 12-26-9, Bollinger 20/2, SMA 200/50,
EMA 20), les constantes de `pead.py` et celles de `short.py` ne se
modifient pas.

Raison : chaque jeu de paramètres a été fixé **avant** son test, avec une
empreinte SHA256 de sa spécification. Les changer après coup invalide le
résultat et transforme le test en recherche — avec 7 paramètres à 5
valeurs, 78 125 combinaisons produisent environ 3 900 faux positifs à
z ≥ 2.

Si une modification de paramètre est demandée : refuser, expliquer qu'il
faut une nouvelle spécification, une nouvelle empreinte et une période de
validation non touchée.

Cette règle est désormais **exécutable**, et sur les **trois**
hypothèses. `audit.empreinte()`, `audit.empreinte_pead()` et
`audit.empreinte_short()` calculent le SHA256 des constantes de chacune ;
`audit.empreintes()` rend les trois d'un coup. `test_moteur` compare
chacune à sa référence gelée, et vérifie en plus que les trois
**documents** de spécification n'ont pas été retouchés — le texte et le
code sont deux choses distinctes, on protège les deux.

Trois empreintes séparées, jamais une seule : quand l'une bouge, on sait
laquelle. Chaque ligne du journal d'audit porte l'empreinte sous laquelle
elle a été écrite. Un résultat ne peut plus être attribué par erreur à un
jeu de paramètres qui ne l'a pas produit.

    py -m equity_scanner.audit --parametres   # les trois jeux, en clair

## Ce qu'il ne faut jamais afficher

- Un pourcentage unique de « chances de gagner ». Toujours l'intervalle
  de confiance de Wilson avec le nombre de trades.
- Un avis « garder / vendre » sur une ligne détenue. **La carte de la
  page STRATEGIE affiche l'état en gros** — « 3 conditions sur 4 sont
  actives » — et rappelle que la spécification ferme à la **première**
  condition atteinte. Citer sa propre règle n'est pas un verdict ; ajouter
  le mot « vends » en serait un. De même, « renforcer la ligne ? » est
  répondu par le compte des 13 blocs d'entrée, jamais par un conseil. `strategie.py`
  donne les **faits** (plus haut atteint, recul depuis ce sommet, part
  du gain rendue, écarts aux moyennes, coût fiscal d'une vente) et
  l'état des **quatre conditions de sortie de la spécification**. La
  différence entre « trois conditions sur quatre sont actives » et
  « vends » n'est pas une nuance de style : la première est vérifiable,
  la seconde est une opinion déguisée.
- Une « meilleure heure pour acheter ou vendre ». `seance.py` donne les
  horaires — ce sont des faits — et deux propriétés structurelles qui ne
  demandent aucune mesure : les écarts sont les plus larges à l'ouverture,
  le plus gros volume passe au fixing de clôture. Tout le reste
  demanderait des données **intraday** que le programme n'a pas : une
  bougie journalière ne contient aucune heure intermédiaire. La
  spécification, elle, exécute à l'ouverture de la séance suivante, et
  c'est ce que le backtest mesure.
- Un chiffrage du risque géopolitique. Les actualités sont du contexte
  pour la vérification avant l'ordre, elles n'entrent dans aucune règle.
- Un score composite construit sur des poids non testés.
- Un verdict directionnel (HAUSSIER / ACHAT) dérivé d'un tel score.
- Une ligne de prédiction de prix. Le cône de dispersion existe : dérive
  fixée à zéro, il donne l'amplitude, jamais le sens.
- Un take-profit **actif**. Les spécifications 2 et 3 disent « aucun
  take-profit », et le motif est mesuré : zéro TP touché, 97 % de sorties
  par autre chose. `horizon.py` mesure ce qu'un objectif **aurait** donné
  sur le titre — fréquence d'atteinte, délai médian, part rendue ensuite.
  Il n'en active aucun. Choisir un niveau parce qu'il sort le mieux sur le
  passé est la pêche que le protocole interdit ; l'activer demande une
  nouvelle spécification, une nouvelle empreinte, une période vierge.
- Un gain espéré en euros tant qu'aucune hypothèse n'a passé sa Phase 0.
  `horizon.gain_espere()` refuse de chiffrer et dit pourquoi : sans
  avantage démontré, le gain espéré vaut zéro, pas un petit nombre
  optimiste.
- Un résultat de `short.py` sans le rappel du dividende non modélisé.
  Une espérance de 0,3 point par trade y ressemble à un avantage ; elle
  est en réalité négative une fois le dividende payé au prêteur.

## État de la validation

- Stratégie 1, « repli en tendance » : **NO-GO** en Phase 0 sur S&P 500
  et 120 titres US. Hypothèse morte, elle ne se retouche pas.
- Stratégie 2, dérive post-annonce (`pead.py`) : spécifiée, moteur codé,
  **test pas encore lancé**.
- Stratégie 3, dérive post-annonce **négative** — vente à découvert
  (`short.py`) : spécifiée (`strategie-short-v1.md`), moteur codé,
  **test pas encore lancé**. Ce n'est pas la stratégie 2 avec les signes
  inversés : perte non bornée, position qui grossit quand elle a tort,
  coût d'emprunt au prorata, dérive haussière du marché à couvrir. Le
  **dividende dû au prêteur n'est pas modélisé** — environ 0,4 point par
  trade d'optimisme à retrancher à la main du résultat affiché.

## Architecture

| Fichier | Rôle |
|---|---|
| `app.py` | serveur HTTP local, page d'accueil, routes API, majordome |
| `chart.py` | page graphique, 4 colonnes, cône de dispersion, **6 unités de temps** dont 5 ANS |
| | une unité est identifiée par sa **clé**, jamais par sa règle de rééchantillonnage : 5 ANS et 1 SEMAINE partagent la taille de bougie, et la déduire de la règle donnait à la seconde les longueurs de la première |
| | la fenêtre affichée sous chaque onglet est **calculée sur les vraies dates** : une constante mentirait dès que l'historique du titre est plus court |
| | `chart.source_trace()` choisit **côté serveur** où prendre la bibliothèque de tracé : la copie locale (`equity_scanner/statique/lightweight-charts.js`) si elle existe, sinon le CDN. **Une seule balise, bloquante.** Jamais de repli `onerror` : il ajouterait le script de façon asynchrone, le code de la page tournerait avant, et la bibliothèque serait toujours absente |
| `hud.py` | éléments visuels : cerf, cadrans, rails, radar |
| `indicators.py` | indicateurs — **PERIODES gelées** |
| `rules.py` | les 13 blocs d'entrée et les 4 sorties |
| `backtest.py` | moteur de simulation, exécution J+1, coûts, **plafond de poids** |
| `phase0.py` | les 5 critères go/no-go |
| `pead.py` | stratégie 2 — **constantes gelées** |
| `short.py` | stratégie 3, vente à découvert — **constantes gelées** |
| `comparatif.py` | système contre SMH buy & hold net de PFU |
| `contexte.py` | faits mesurés d'un titre, sans score inventé |
| `positions.py` | registre manuel des positions |
| | chaque ligne porte sa **devise de cotation** (déduite du suffixe de place) et un **contrôle de cohérence** du prix d'entrée : s'il n'est jamais tombé dans l'intervalle parcouru par le titre, la carte le dit et prévient que le gain latent affiché est faux |
| `news.py` | Alpha Vantage — quota 25/jour, caches obligatoires |
| | la clé est rangée **deux fois** : `.bruce_cache` à côté du programme, et `~/.carruos/` — cette seconde copie est la seule qui survive à une mise à jour, `.bruce_cache` n'étant pas livré dans l'archive |
| | `app.retrouve_cle()` va la chercher dans une installation **voisine** si les deux manquent. Portée volontairement étroite : un seul niveau au-dessus du programme plus quelques dossiers usuels, deux niveaux de profondeur, plafond de 400 dossiers, un seul nom de fichier lu. Elle ne tourne **jamais** si `~/.carruos/` existe déjà — sinon effacer volontairement la clé la ferait ressusciter au lancement suivant |
| | **aucune clé ne doit entrer dans le dépôt.** `.bruce_cache/` est ignoré et `test_pages` refuse tout jeton de 16 majuscules dans un fichier suivi par git |
| `data.py` | chargement yfinance, 8 univers, compositions figées |
| `cache.py` | cache disque et téléchargements parallèles |
| `qualite.py` | refus de signal sur données douteuses |
| `audit.py` | journal des signaux, empreinte des paramètres |
| `robuste.py` | stabilité, Monte Carlo, bootstrap par blocs |
| `calibration.py` | met le critère 4 à l'épreuve sur du bruit pur |
| `horizon.py` | amplitude par horizon, objectif atteignable, entrée en euros |
| `seance.py` | horaires des 9 places, fériés **calculés**, heure d'été suivie |
| `strategie.py` | projection de réinvestissement, revue de ligne |
| | la projection sépare **ce que vous versez** de **ce que le fonds capitalise tout seul**, année par année, et donne l'année où le second dépasse le premier |
| `reglages.py` | **13 thèmes**, 13 effets visuels débrayables |
| | un thème porte une `forme` : biseau, arrondi, équerres, densité, matière, typographie. Les valeurs par défaut **sont** l'apparence d'origine, donc un thème qui n'en redéfinit aucune ne change rien |
| | **aucun thème clair** : ce n'est pas au goût du propriétaire, et `test_pages` le vérifie |

## Chantiers

1. **Univers historiques** — *outillé, à alimenter.*
   `data.figer_univers()` enregistre la composition du jour, datée ;
   `univers_a_la_date()` relit la plus proche avant une date donnée.
   On ne peut pas remonter le temps : il faut lancer
   `py -m equity_scanner.data --figer sp500` **chaque trimestre** pour
   construire l'historique qui manque. Tant qu'aucune composition
   d'époque ne couvre le début de la période testée, la Phase 0 affiche
   l'avertissement de biais du survivant en tête de rapport.
2. **Contrôle qualité des données** — *fait.* `qualite.py`, câblé dans
   `scan`, `app._scan`, `phase0` et `pead`. Un titre refusé ressort
   toujours avec son motif.
3. **Journal d'audit** — *fait.* `audit.py`, une ligne par signal évalué.
4. **Walk-forward et Monte Carlo** — *fait.* `robuste.py`, joint
   automatiquement au rapport de Phase 0.
5. **Plafond de poids par ligne** — *fait.* Il était écrit dans les trois
   spécifications (25 % à l'achat, 20 % à la vente) et appliqué par
   `rules.size_position()` pour le scan du jour, mais le backtest
   dimensionnait au seul risque : sur données d'essai, **un quart des
   lignes dépassaient le plafond**, et un stop très serré produisait une
   position à 200 % du capital. `backtest.portefeuille(max_poids=…)`
   l'applique maintenant à l'entrée, et le rapport dit combien de lignes
   ont été réduites.

   Pour la vente à découvert, la spécification demande une vérification
   **en continu** sans écrire quel ordre passer au franchissement.
   `backtest.poids_observes()` **mesure** donc le poids atteint séance par
   séance et le rapporte ; il ne corrige rien. Écrire la règle de
   réduction demande une nouvelle spécification, avant le prochain test.

6. **Le témoin du critère 4** — *mesuré, pas tranché.* L'étape 6 du
   protocole dit : « on remplace les signaux d'entrée par 1 000 tirages
   aléatoires, on garde **exactement les mêmes règles de sortie** ». Le
   code ne le faisait pas : il tenait la position une durée fixe, sans
   stop ni sortie de tendance. Les deux témoins existent désormais
   (`z_contre_hasard` pour celui du texte, `z_duree_appariee` pour
   l'ancien) et le rapport affiche les deux.

   Ils ne donnent pas le même z — l'écart va de quelques dixièmes à près
   de deux points, et le témoin conforme au texte est **le plus facile à
   battre** dans presque tous les univers mesurés. Lequel est le mieux
   centré sur du bruit n'est pas tranché : à une dizaine d'univers,
   l'écart-type du z est de 1 à 2, donc aucune moyenne n'est fiable.

   En attendant, `phase0.z_retenu()` retient le **plus défavorable** des
   deux. C'est une règle écrite avant le prochain test et qui ne peut que
   rejeter davantage — donc impossible à jouer dans le bon sens.
   `py -m equity_scanner.calibration` refait la mesure à la demande.

   Le point de calibration du protocole — « cours purement aléatoires,
   z = +0,93 » — a été établi avec l'ancien témoin. **Trancher demande
   une nouvelle spécification**, pas un choix après coup.

7. **Scalp et day trading** — *bloqué sur les données, et sur une
   question.* `intraday-v1-BROUILLON.md` fait l'état des lieux. Ce n'est
   **pas** une spécification et ça ne doit pas être traité comme telle :
   aucun seuil n'y est gelé, aucune empreinte ne le couvre.

   Deux verrous. Le premier est matériel : yfinance donne 7 jours de
   bougies 1 minute, Alpha Vantage gratuit plafonne à 25 appels/jour.
   Un historique intraday utilisable coûte environ 50 €/mois.

   Le second est le vrai : **qui est en face ?** En journalier, la
   contrepartie est contrainte (fonds indiciels, mandats de style,
   prises de profit) et pas mieux informée. En intraday, c'est un
   teneur de marché automatisé qui voit le carnet et dont le métier est
   de gagner le spread. Tant que cette question n'a pas de réponse
   écrite, le protocole dit de s'arrêter — c'est elle qui a tué la
   stratégie 1.

   Aucun signal intraday ne sort du programme tant que ce brouillon n'a
   pas été remplacé par un `intraday-v1.md` daté et haché.

8. **Corporate actions** au-delà des splits : changements de ticker,
   fusions, retraits de cote. `qualite.py` **détecte** une division non
   ajustée et une interruption de cotation, et refuse le signal ; il ne
   sait pas encore recoller un historique après un changement de ticker.
   C'est le chantier qui reste entier.

## Contraintes techniques

- Python 3.11 — pas de syntaxe 3.12+ (attention aux f-strings avec
  antislash).
- **Aucun antislash dans une chaîne JavaScript non brute.** `JS` de
  `chart.py` est une chaîne Python ordinaire : `\\statique\\` y devient
  `\statique\`, et JavaScript avale `\s` et `\l` sans rien dire. Un
  chemin Windows s'affichait collé. Utiliser des barres obliques —
  Windows les accepte aussi.
- **Un script externe se charge de façon BLOQUANTE, ou il arrive trop
  tard.** Un repli qui fait `document.createElement("script")` dans un
  `onerror` est asynchrone : le code de la page s'exécute avant, ne
  trouve rien, et affiche son message de secours même avec une connexion
  parfaite. C'est exactement ce qui est arrivé. Quand le choix dépend de
  l'environnement, c'est le **serveur** qui tranche à la fabrication de
  la page, pas le navigateur à l'exécution.
- **Un test peut valider une mécanique et rater ce qu'elle produit.** Le
  test du repli vérifiait que la fonction était définie avant la balise —
  elle l'était — sans jamais vérifier que la bibliothèque finissait par
  être là. Vérifier le résultat, pas le montage.
- **Le rendu ne suffit pas, il faut regarder.** Trois défauts de thème
  n'ont été vus que sur les captures : des équerres qu'une animation
  rallumait malgré `--equerre:0`, des champs de saisie restés sombres sur
  le thème clair, un mot invisible. Aucun test ne les voyait.
- **`transition:.18s` sans nom de propriété vaut `transition: all`** — le
  navigateur anime alors aussi la largeur, le remplissage et la police
  quand ils changent. C'était le cas à cinq endroits, et c'est une des
  causes du « visuel qui saute ». Nommer les propriétés. `test_pages` le
  vérifie.
- **Une colonne de grille en `auto` suit son texte.** La première colonne
  des rails était en `auto` : au rafraîchissement, un libellé plus long
  décalait toute la grille. Largeur fixe, et `tabular-nums` sur les
  chiffres pour que `0/5` et `12/5` occupent la même place.
- Toute animation CSS doit porter sur `transform` ou `opacity`. Animer
  `top`, `left`, `width` ou `background-position` fait sauter la page
  entière. `test_pages` le vérifie.
- Les chaînes JavaScript dans le code Python doivent être des chaînes
  **brutes** (`r"""`). Sinon `\'` devient une apostrophe nue et casse
  tout le script de la page.
- Ne jamais réutiliser un alias de module comme variable locale.
  `test_pages` le vérifie aussi.
- Un thème ne fait qu'**outrepasser** les règles de base, par une classe
  `theme-…` sur `<body>`. Rien n'est retiré : un thème inconnu retombe
  proprement sur l'apparence d'origine. Les couleurs qui doivent suivre
  le thème passent par `var(--acc)`, `var(--pos)`, `var(--neg)` ou
  `var(--holo)` — jamais par un code hexadécimal figé, sinon l'élément
  reste cyan sur un fond violet.
- Les téléchargements passent par `cache.charge()` ou `cache.charge_lot()`,
  jamais par `data.load_yf()` en direct : sinon le même titre repart sur
  le réseau à chaque écran. Un module de test qui veut des données
  synthétiques remplace `data.load_yf` ; `data.loader()` résout la
  fonction à l'appel pour que cette substitution fonctionne.
