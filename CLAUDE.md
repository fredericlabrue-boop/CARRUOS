# CARRUOS — contexte pour Claude Code

Scanner d'actions personnel de Frédéric, affiché sous le nom
**CARRUOS ALICE** (`app.ALIAS`). « Repli en tendance » reste le nom de
l'hypothèse 1 dans `rules.py` et l'audit — un nom de résultat ne se
renomme pas après coup. Python, interface HTML servie en
local et affichée dans une fenêtre pywebview.

## Lancer

```
py -m equity_scanner.app          # l'application
py -m equity_scanner.test_pages   # contrôle des pages générées
py -m equity_scanner.test_rules   # contrôle des règles
py -m equity_scanner.test_moteur  # contrôle du moteur

py -m equity_scanner.chandeliers NVDA   # figures, et ce qui a suivi
py -m equity_scanner.options NVDA       # open interest des OPTIONS
py -m equity_scanner.palmares COIN HOOD TLX.DE   # les 13 blocs, classés
py -m equity_scanner.dossier "je sors quand sur TLX.DE"
py -m equity_scanner.pead         # stratégie 2 : préparation, puis passage unique sur OUI
py -m equity_scanner.short --valider-documents   # stratégie 3 : note de lecture et amendement, une fois
py -m equity_scanner.short        # stratégie 3 : préparation, puis passage unique
py -m equity_scanner.short --abandonner   # stratégie 3 : l'abandon, inscrit au registre
py -m equity_scanner.decision TLX.DE 20000 2 mois   # AVANT L'ORDRE : taille, stop, faits
py -m equity_scanner.detention TSLA 2 mois   # ce que cette durée a donné, contre l'indice
py -m equity_scanner.faillites   # RESTRUCTURATIONS : les 8-K item 1.03 et ce qui a suivi
py -m equity_scanner.recherche nasdaq100 800 50 "1 semaine"   # somme, gain visé, durée
py -m equity_scanner.recherche us_europe 3000 100 "1 mois" rebond   # + une situation
py -m equity_scanner.rebond TLX.DE 25   # après une chute de 25 % : ce qui a suivi, sur ce titre
```

`MEMO-LECTURE.md` à la racine rassemble **tous les seuils** du
programme. `test_moteur` vérifie que chaque nombre qui y est cité est
celui qui tourne réellement : un mémo qui dérive du code est pire
qu'aucun mémo, il donne confiance dans un chiffre faux.

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
  `veille.py` **rapproche** l'actualité de ses lignes — il ne l'analyse
  pas. Trois niveaux, étiquetés par leur force : **nommé** (la source
  déclare elle-même que l'article porte sur ce titre), **même secteur**
  (correspondance de *noms*, par une table écrite d'avance et affichée
  avec le résultat), **mot trouvé** (un appariement de chaînes, et rien
  d'autre). Le niveau 3 est le dernier et s'appelle « mot trouvé » parce
  qu'Alpha Vantage **n'étiquette pas la géopolitique** : il faut aller
  chercher les mots soi-même, et c'est nettement plus faible. Aucun
  total n'est calculé — compter des occurrences donnerait un nombre qui
  ressemblerait à une mesure sans en être une. `test_moteur` retire du
  texte tout ce que la veille **recopie** de la dépêche et exige qu'il
  ne reste aucun chiffre.
- **Le ton d'une actualité présenté comme une mesure.** Alpha Vantage
  étiquette chaque article — *Bullish* … *Bearish*. La page d'accueil
  l'a affiché, puis retiré (verdict directionnel d'un score composite
  aux poids inconnus). Le **propriétaire l'a redemandé le 25 septembre
  2026** : « positif ou négatif face aux annonces ». C'est sa décision,
  tenue à quatre conditions qui en font une **étiquette** et non une
  mesure : c'est le **mot du fournisseur** traduit mot pour mot, par
  **ses** seuils publiés (`news.TONS`, `news.libelle_sentiment`) ; il
  est **attribué à chaque affichage** (« selon Alpha Vantage », au
  survol et sous la liste) ; **rien ne s'en sert** — ni règle, ni tri,
  ni compte, ni la jointure de la veille, ni le dossier du majordome ;
  le score brut reste lisible au survol. `test_moteur` vérifie les
  quatre. Il ne dit pas que le cours va monter : c'est un classement du
  **vocabulaire** de l'article, et une information publique est déjà
  dans les cours quand on la lit.
- Un score composite construit sur des poids non testés.
- Un verdict directionnel (HAUSSIER / ACHAT) dérivé d'un tel score.
- **Un « avis » ou un « intérêt » qui soit autre chose qu'un compte.**
  `interet.py` répond à la demande d'un avis à chaque consultation, et
  y répond par quatre comptes : combien des 13 blocs passent, avec pour
  chaque bloc manquant **la valeur mesurée en face de son seuil** ;
  les vetos d'éligibilité ; le même décompte aligné sur les six unités
  de temps, sans pondération ; l'historique du signal sur ce titre avec
  son intervalle de Wilson. L'échelle à sept marches est écrite dans
  `interet.NIVEAUX`, avant tout usage, et chaque marche porte le nom
  de son compte — « IL MANQUE PEU » se vérifie, « ACHETER » non.
  Deux phrases accompagnent la carte à chaque affichage : qu'aucune
  hypothèse n'a passé sa Phase 0, et que ce n'est pas un avis.
- **Ce qu'une figure de chandelier « annonce ».** `chandeliers.py`
  détecte dix-sept figures — marteau, pendu, harami, avalement,
  pénétrante, nuage noir, étoiles, trois soldats — parce qu'une figure
  est une relation **géométrique**, vérifiable à la règle. Il n'écrit
  jamais qu'un marteau est haussier : il MESURE ce que la figure a été
  suivie de **sur ce titre**, et l'affiche à côté du **taux de base**
  du titre. Sans cette comparaison, « 56 % de hausses après un
  marteau » ne dit rien sur un titre qui monte 56 % du temps. Quand
  l'intervalle de Wilson contient le taux de base, la figure est
  déclarée **indiscernable du hasard**.
  Et le **piège des comparaisons multiples est affiché, pas tu** :
  17 figures × 4 horizons ≈ 72 mesures par titre, donc environ 4
  « écarts nets » sont attendus **par le seul hasard**. Vérifié sur
  12 univers de bruit pur : 4,5 % des mesures ressortaient nettes,
  contre 5 % attendus. Un écart net isolé ne vaut rien.
- **Un open interest sur une action.** Elle n'en a pas : c'est une
  notion de contrats à terme et d'options, et une action existe en
  nombre fixe. `options.py` lit celui des **options** du titre (total
  calls/puts, rapport put/call, strikes les plus chargés) et dit en
  tête que la photo du jour ne se compare à rien, faute d'historique
  collecté. Pour l'action elle-même, la notion voisine est le volume
  rapporté à son habitude, mesuré par `chandeliers.volume_prix()`
  contre le même taux de base.
- **Un classement « des plus pertinentes aux moins »**, s'il vient d'une
  somme de critères pondérés. La page **MA LISTE** (`palmares.py`) range
  des titres collés à la main, et son tri par défaut est celui que la
  **spécification écrit déjà** — `rules.rank()`, force relative 6 mois —
  avec l'avertissement que ce code porte lui-même : c'est un
  **départage**, pas un signal validé, et il ajoute un degré de liberté
  qui n'a pas passé la Phase 0. Les quatre autres tris portent **chacun
  sur un seul fait** (blocs remplis, risque, R mesuré, alphabétique) :
  un tri sur un fait se vérifie, une somme pondérée non.
- **Un « ratio risque / gain ».** Il n'y en a pas, parce que la
  spécification **n'a aucun objectif de gain** : elle dit « aucun
  take-profit ». Ce que MA LISTE affiche en face du risque — défini par
  la spec, `(entrée − stop) / entrée` — c'est ce que ce signal a
  **réellement rendu sur ce titre** : gagnants sur trades, intervalle de
  Wilson, R moyen, profit factor. Un relevé, pas une promesse, et sur
  une hypothèse qui a rendu NO-GO.
- **Un avis, même quand la question en demande un.** « Que penses-tu de
  TLX ? » est une invitation directe, et une IA branchée sur des cours y
  répond en inventant : *« bien orienté, momentum qui se retourne,
  sortie vers 380 »*. Aucun de ces mots ne vient d'une mesure.
  Le majordome répond par `dossier.py`, et l'intention `avis` ne rend
  **pas** un avis : elle rend la fiche complète — les 13 blocs et leurs
  manques chiffrés, les 4 conditions de sortie et leur état, le stop,
  l'historique du signal avec son intervalle — suivie du rappel
  qu'aucune hypothèse n'a passé sa Phase 0.
  La règle qui rend cela tenable : **l'IA ne voit jamais les cours**.
  Elle reçoit un dossier de faits déjà calculés et ne fait que le
  router. Si l'on ajoute un jour un modèle de langage, c'est ce contrat
  qu'il faut préserver : router et mettre en phrases, jamais produire un
  chiffre.
- **Un chiffre produit par le modèle de langage.** Le cerveau
  (`cerveau.py`) **met en phrases et route**, il ne calcule rien. La
  version précédente de ce module *demandait* au modèle de ne rien
  inventer ; demander ne suffit pas. Trois garde-fous, dans cet ordre :
  les **faits d'abord** — `dossier.py` calcule la réponse déterministe
  AVANT tout appel réseau, et elle s'affiche quoi qu'il arrive au
  modèle, clé absente, API en panne ou réponse de travers ; le modèle
  **ne voit jamais les cours**, seulement un dossier de faits déjà
  calculés, donc il ne *peut* pas « lire le graphique » ; et
  `verifie_chiffres()` confronte chaque nombre de la réponse au dossier
  envoyé et **nomme** ceux qui n'y figurent pas. Ce n'est pas un filtre,
  c'est une étiquette : le lecteur voit ce qui remonte à une mesure.
  Le modèle ajoute de la prose par-dessus les faits ; il ne les
  remplace jamais.
- **Une consigne de modèle qui l'autorise à trancher.** La version 29,
  écrite ailleurs, avait remplacé la consigne par celle d'un « trader
  fictif de 50 ans d'expérience » chargé de donner un « avis de travail »
  sur « je garde ? », d'expliquer ce qu'une bougie « signifie » et de
  choisir un horizon. Chacune de ces trois choses est interdite plus
  haut, et pour la même raison : le modèle ne voit pas les cours, et
  aucune hypothèse n'a passé sa Phase 0. La consigne garde le ton du
  mentor — faits, lecture selon la spécification, ce qui manque, ce qui
  changerait le tableau, les questions à se poser — et **aucun**
  verdict. `test_moteur` vérifie que chaque ligne rouge y figure : une
  consigne se réécrit en une minute, et rien d'autre ne le verrait.
- **Aucune clé API dans le programme.** CARRUOS n'en embarque aucune et
  ne peut pas en fabriquer. Celle du cerveau est celle du propriétaire,
  prise chez le fournisseur, rangée dans `~/.carruos/ia.json` en 0600 —
  jamais dans le code, jamais dans le dépôt, jamais dans l'archive
  livrée. Elle ne repart jamais vers la page, et `test_pages` le
  vérifie.
- **Un avis sur le type d'un instrument.** « Une action Tesla ne se
  traite pas comme un ETF monde » est vrai, donc ça se **mesure**.
  `profil.py` donne l'amplitude, l'écart quotidien ordinaire, le pire
  recul et le temps de retour, le bêta et la corrélation — et surtout
  la **durée réelle** des positions que les règles de la spécification
  produisent sur ce titre. L'horizon n'est pas un choix qu'on fait :
  c'est une **conséquence** des quatre conditions de sortie. Le type
  déclaré par la source de données est signalé comme une *déclaration*,
  pas comme une mesure ; les autres lignes ne dépendent d'aucun
  libellé. Aucun score composite ne les résume : chaque mesure se lit
  seule.
- **Le mot « impossible » devant un objectif chiffré.** L'arithmétique
  ne dit jamais impossible, elle dit **ce que ça demande**.
  `objectif.py` fixe deux leviers sur trois — capital, versement, taux
  et temps — et résout le troisième exactement. Il rend le taux exigé,
  le versement exigé, la durée au taux posé en hypothèse, et le seul
  chiffre qui ne dépende d'aucune hypothèse : la durée par les seuls
  versements. Le taux exigé est ce que l'équation réclame, **jamais ce
  qu'un placement va rendre**, et le programme ne dit pas où le
  trouver. Le taux net d'impôt se **résout**, il ne se déduit pas d'une
  division par (1 − PFU) : le prélèvement frappe le gain une fois, à la
  sortie, et le raccourci surestime l'effort.
- **Une note du carnet interprétée.** `carnet.py` range ce que le
  propriétaire écrit et n'y touche pas. Un **relevé** est autre chose :
  une photo datée de ce que le moteur mesurait à l'instant où elle a
  été figée, calculée **côté serveur**. Prise dans le navigateur, elle
  photographierait ce que la PAGE affichait au lieu de ce que le moteur
  a MESURÉ — et c'est exactement la confusion qu'un carnet doit
  empêcher. Le carnet ne dit jamais « vous aviez raison ce jour-là » :
  comparer une intention à un résultat demanderait de décider ce qui
  compte comme réussite, ce qui est un avis, pas une mesure.
- **Un ordre passé depuis CARRUOS.** L'onglet IBKR **lit** le compte
  en direct ; il ne peut rien y envoyer, et ce n'est pas une promesse
  mais trois verrous. La session est ouverte en `readonly=True`, le
  drapeau de l'API d'IBKR elle-même : TWS refuse tout ordre qui en
  vient. Aucun nom d'ordre (`placeOrder`, `cancelOrder`, `Order`,
  `LimitOrder`… la liste `ibkr.ORDRES_INTERDITS`) n'apparaît dans
  `ibkr.py` — `test_moteur` le lit comme un **arbre syntaxique**, pas
  comme du texte, sinon la liste elle-même se ferait refuser. Et
  `ibkr.py` est la **seule porte** : aucun autre module n'importe la
  bibliothèque IBKR. Vérifié par mutation sur les trois : ajouter un
  `placeOrder`, passer `readonly` à `False`, ou importer `ib_async`
  ailleurs fait chacun tomber son test. On conseille en plus de cocher
  « Read-Only API » dans TWS : un quatrième verrou, côté IBKR.
- **Un cours différé présenté comme frais.** IBKR ne donne le temps
  réel qu'avec l'abonnement de la place ; sans lui, le cours a 15 à
  20 minutes de retard. Chaque cours porte son **type**, tel que TWS le
  déclare — TEMPS RÉEL, DIFFÉRÉ, FIGÉ — collé au chiffre. Le flux
  « compte » d'IBKR ne se rafraîchit qu'environ toutes les trois
  minutes : chaque ligne est donc abonnée à son propre cours et à son
  P&L du jour, qui suivent le marché.
- **« Compte réel » ou « simulation » deviné d'après le port.** Il se
  lit sur le **numéro de compte** — « DU… » pour la simulation. L'ancien
  `portefeuille.py` le déduisait du port : IB Gateway en simulation
  (4002) s'y affichait RÉEL. Et la page montre le port de la session
  **en cours**, pas le dernier réglage enregistré : un sélecteur sur
  « 7497 — simulation » à côté de « CONNECTÉ — COMPTE RÉEL » était
  exactement la confusion à rendre impossible.
- **Un seuil ajusté par la mémoire.** « Quand il a loupé une action
  qui a explosé, il apprend » : la réponse tentante est d'assouplir le
  bloc qui l'a écartée, et de recommencer à chaque fusée. Au bout de six
  mois le filtre ne filtre plus rien — il a été ajusté sur un passé
  qu'il connaît déjà. `memoire.py` tient le **compte complet** : chaque
  état écrit au journal d'audit **avant** que le titre ne bouge, rangé
  après coup dans l'une des quatre cases (signal confirmé, faux signal,
  occasion manquée, piège évité). Il ne touche à **aucun** seuil —
  `test_moteur` vérifie par l'AST qu'il n'écrit l'attribut d'aucun
  module. Ce qu'il révèle est, au mieux, l'idée d'une nouvelle
  spécification.
- **Une occasion manquée affichée seule.** On se souvient de l'action
  qu'on n'a pas achetée, pas des quarante au même profil que le filtre a
  écartées et qui se sont effondrées. Les occasions manquées sont
  **toujours** en face des pièges évités, **en même nombre** — même quand
  l'une des colonnes est plus longue. Le cerveau a la même consigne :
  jamais une fusée manquée citée seule.
- **« La bonne durée » pour un titre, ou « c'est bien de le garder ».**
  « Tesla, je garde deux mois, c'est bien ? » ; « celui-là c'est plutôt
  une semaine, celui-là un an ». La première moitié se mesure :
  `detention.py` rend, pour la durée que le propriétaire tape, ce que
  chaque période **non chevauchante** de cette durée a donné sur tout
  l'historique — combien en hausse avec leur Wilson (rien sous 8
  périodes), la médiane, le pire, le recul **en chemin**, et le même
  compte contre l'indice sur les mêmes dates — puis les cinq durées
  usuelles **dans un ordre fixe**, jamais triées sur leur résultat, et
  « acheté lundi, vendu vendredi » contre le taux de base du titre. La
  seconde moitié ne se mesure pas : désigner après coup la durée qui a
  le mieux marché est la pêche que le protocole interdit, et cinq durées
  comparées donnent cinq chances d'en voir une briller par hasard. La
  carte et le majordome le disent à chaque réponse.
- **Un « potentiel » parmi les sociétés en faillite.** « Scanne toutes
  les entreprises en faillite avec des plans de relance, les bangers,
  comme le trader japonais. » `faillites.py` dresse la liste des
  **faits** : chaque 8-K **item 1.03** déposé à la SEC sur 18 mois, le
  plan **confirmé** quand un dépôt *postérieur* cite l'ordonnance, l'item
  **3.03** (droits des actionnaires modifiés, le plus souvent annulés),
  le lien vers chaque dépôt, et ce que le cours a fait depuis la veille
  du dépôt — **coupé à la veille du 3.03**, au-delà duquel le cours peut
  être celui d'actions nouvelles. Le **compte complet** l'accompagne, y
  compris les tickers sans cours et les sociétés sans ticker, qui sont
  souvent les pires : on entend parler du titre multiplié par dix, pas
  des dizaines qui ont fini à zéro. Tris sur un seul fait, aucun score,
  et le rappel qu'un Chapter 11 laisse souvent **rien** aux anciens
  actionnaires. L'Europe n'a pas de registre qui relie procédures et
  cote : les titres s'y ajoutent à la main.
- **« Les actions qui feront +50 € cette semaine ».** « Je mets 800 €,
  je veux +50 € en une semaine, scanne-moi des actions US et Europe. »
  `recherche.py` passe l'univers à la question qui se mesure : la somme
  devient un nombre **entier** d'actions au cours du jour converti en
  euros, le gain et la même perte deviennent le mouvement qu'ils
  demandent **nets des frais du backtest**, puis sur chaque période non
  chevauchante de la durée : gain touché, perte touchée, lequel
  **d'abord**, fin au gain — chaque proportion avec son Wilson. La
  colonne de la perte est **toujours** à côté de celle du gain, le
  marché aux mêmes seuils sert de repère, et la page **mesure** sur sa
  propre liste la corrélation entre les deux colonnes : toucher un seuil
  est d'abord de l'amplitude, dans les deux sens. Tris sur un fait
  unique. « Une heure » est proposée et **refusée avec sa raison**
  (aucun historique intraday, chantier 7) — plutôt que remplie avec des
  chiffres qui n'existent pas. Les titres du propriétaire s'y ajoutent —
  ceux qu'il tape, et ses lignes **détenues** (registre, IBKR), mesurées
  sur leur **quantité réelle** et non sur la somme — dans un tableau à
  part, en tête. Un ticker tapé sans place est pris tel quel, jamais
  « corrigé » : « TLX » est Telix à New York, pas Talanx ; quand le
  propriétaire détient TLX.DE, la ligne le **dit** à côté.
- **Ce qu'une suite de bougies « annonce ».** « Marteau, étoile filante :
  ça annonce une hausse ? » La bande **sous le RSI** pose une pastille
  sous chaque bougie où une figure est détectée, sur l'unité affichée ;
  sa couleur dit ce que la figure a été **suivie de sur ce titre** à
  5 barres — grise dans le bruit, verte ou rouge pour un écart net — et
  le survol donne la phrase complète contre le taux de base, avec le
  compte des écarts nets attendus par hasard. Jamais « annonce ».
- **« Il va rebondir », « c'est bien d'acheter la baisse », « ce nouveau
  modèle va faire monter l'action ».** Le propriétaire l'a demandé le 29
  septembre 2026 : une IA qui lui dise « oui, rebond », « oui, achète ».
  C'est exactement l'avis que ce projet refuse, et la consigne du modèle
  le refuse aussi. Ce qui se mesure est rendu : `rebond.py`, chaque
  épisode passé où **ce** titre est tombé d'autant sous son sommet, et
  ce qui a suivi à 1, 3, 6 et 12 mois contre un jour quelconque, avec le
  rappel qu'un titre encore coté s'est **par construction** relevé de
  ses chutes. Pour une annonce, les articles qui nomment le titre, et le
  rappel qu'elle est dans les cours quand on la lit.
- **« Cette action te correspond », « on est en crise », « en temps de
  crise, prends celle-là ».** Demandé le 29 septembre 2026 : « je rentre
  mes paramètres — 100 € sur 3 000 €, une action en crise avec un rebond
  confirmé, ou haussière mais pas à son pic — et il me conseille ». La
  moitié qui se mesure est faite : la **situation** est un critère que le
  propriétaire choisit et règle (`recherche.SITUATIONS`, seuils X, Y, Z1,
  Z2), lu sur les clôtures **jusqu'au jour dit** ; la page garde les
  titres qui y sont aujourd'hui et mesure ce que sa durée a donné
  **dans cette situation**, contre une période quelconque du même titre,
  avec le compte des écarts nets attendus par hasard. « Rebond
  confirmé » ne se sait qu'après coup : la page dit « rebond amorcé,
  remonté de Y % depuis le plus bas de 3 mois ». Le mot « haussière »
  n'est pas repris (mot de direction) : « en tendance, pas à son
  sommet », défini par ses faits. « Crise » n'a pas de définition
  mesurable : le marché est rendu en **faits** (écart à la moyenne 200
  séances, recul sous le plus haut d'un an, volatilité rangée dans son
  historique) avec la seule règle écrite d'avance — la spécification
  n'autorise aucune entrée sous la moyenne 200 de l'indice. Aucun titre
  n'est désigné, et la consigne du modèle l'interdit aussi.
- **Un « feu vert » avant l'ordre.** « Fais-moi une stratégie qui
  m'aide dans la prise de décision » (30 septembre 2026). AVANT L'ORDRE
  (`decision.py`) prépare un achat que le **propriétaire** envisage : la
  taille par ses deux règles de risque (1 % au stop, 25 % par ligne, lues
  dans `rules.py`), les faits du titre, et une liste de huit points
  écrite d'avance (`decision.QUESTIONS`) dont trois qu'il écrit ou coche
  — pourquoi, ce qui le ferait dire qu'il avait tort, la perte acceptée.
  Huit sur huit veut dire **préparée**, jamais « bonne » : la page le dit
  à chaque affichage. La décision s'écrit au carnet avec les faits
  **recalculés côté serveur**, pour qu'un jour la mémoire mesure ses
  décisions en entier.
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
- Stratégie 2, dérive post-annonce (`pead.py`) : **NO-GO** au passage
  unique du 29 septembre 2026 sur 2024-2026 (z +1,13, profit factor 1,13,
  drawdown 32,6 %), inscrit au registre. Hypothèse morte. Le moteur qui a
  tourné (`4f038443…`) est archivé à l'octet près dans `archives/`, et
  `test_moteur` vérifie son empreinte. Ce passage a révélé deux défauts de
  **données**, corrigés depuis pour les hypothèses suivantes : le Nasdaq 100
  manquait à l'univers « us » (503 titres sous l'étiquette « S&P 500 +
  Nasdaq 100 »), et 8 ans de cours ne couvraient de la répétition
  2010-2021 que 2019-2021.
- Stratégie 3, dérive post-annonce **négative** — vente à découvert
  (`short.py`) : spécifiée (`strategie-short-v1.md`), moteur **relu contre
  son texte le 30 septembre 2026** (`strategie-short-v1-lecture.md`, datée
  et hachée, aucune constante n'a bougé : `47d593c5…`), documents validés
  par le propriétaire le 30/09. **Répétition 2010-2023 NO-GO** : −1,95 %
  par trade contre −1,99 % pour le témoin (z +0,17), PF 0,64 — 0,75 sans
  aucun frais —, recul maximal 84,4 %. Le passage unique **n'est pas
  parti** : 409 titres exploitables sur 518, sous les 80 % de la note de
  lecture ; rien de 2024-2026 n'a été regardé. **ABANDONNÉE**, inscrite
  au registre par le propriétaire le 30 septembre 2026 (`--abandonner`,
  choix 4 de `Tester-strategie-3.bat`), comme un échec, sans période
  consommée. Une hypothèse abandonnée ne repart plus. Le budget 2026 est épuisé :
  `pistes-2027-BROUILLON.md` rassemble ce que les trois échecs ont appris. Sa période de validation,
  2024-2026, a été regardée par la stratégie 2 le 29/09 ;
  `strategie-short-v1-amendement-1.md` en tire les conséquences — les
  règles de H3 étaient gelées depuis le 18/09, et le protocole consomme une
  période **par hypothèse**. Le passage ne part pas tant que le
  **propriétaire** n'a pas validé les deux documents
  (`--valider-documents`, liée à leurs empreintes) et déclaré n'avoir
  jamais lancé l'ancienne voie directe, qui calculait sur 2024-2026 sans
  registre. Si cette déclaration ne peut pas être faite, la période est
  brûlée pour H3 : il faut une spécification v1.1 à période vierge.
  C'est la troisième hypothèse de 2026 — la dernière du budget annuel.
  Ce n'est pas la
  stratégie 2 avec les signes inversés : perte non bornée, position qui grossit quand elle a tort,
  coût d'emprunt au prorata, dérive haussière du marché à couvrir. Le
  **dividende dû au prêteur n'est pas modélisé** — environ 0,4 point par
  trade d'optimisme à retrancher à la main du résultat affiché.

## Architecture

| Fichier | Rôle |
|---|---|
| `app.py` | serveur HTTP local, page d'accueil, routes API, fenêtres |
| | chaque fenêtre fille est créée **avec** `js_api` et porte son titre (« CARRUOS ALICE — STRATÉGIE ») ; son logo est posé par la propriété `Icon` de sa fenêtre WinForms, à l'événement `shown` (`_icone_fenetre`), et `_veille_icones` le repose sur toute fenêtre du processus qui l'a repris |
| | `_raccourci_auto` pose le raccourci du Bureau au premier lancement, et le repose quand le logo change (marque `~/.carruos/raccourci.json`, taille de l'icône) |
| `chart.py` | page graphique, 4 colonnes, cône de dispersion, **6 unités de temps** dont 5 ANS |
| | une unité est identifiée par sa **clé**, jamais par sa règle de rééchantillonnage : 5 ANS et 1 SEMAINE partagent la taille de bougie, et la déduire de la règle donnait à la seconde les longueurs de la première |
| | **quatre** graphiques alignés (`TOUS`) : prix, RSI, la **bande des bougies** (`_bougies`, figures des barres affichées et leur suivi par `chandeliers.suivi`), MACD. La bande n'a pas d'axe du temps et son texte est posé **sur** elle |
| | la fenêtre affichée sous chaque onglet est **calculée sur les vraies dates** : une constante mentirait dès que l'historique du titre est plus court |
| | `chart.source_trace()` choisit **côté serveur** où prendre la bibliothèque de tracé : la copie locale (`equity_scanner/statique/lightweight-charts.js`) si elle existe, sinon le CDN. **Une seule balise, bloquante.** Jamais de repli `onerror` : il ajouterait le script de façon asynchrone, le code de la page tournerait avant, et la bibliothèque serait toujours absente |
| `hud.py` | éléments visuels : cerf, cadrans, rails, radar, **icône** |
| | `hud.holo_calques()` dessine **l'hologramme de l'accueil en petit** — anneaux, lueur, cône, socle, cerf en trait net sur halo avec son aberration chromatique. `hud.icone()` le pose en **médaillon** sombre (onglet, fenêtres, `carruos.ico`) ; le majordome en fait son avatar, calque par calque. Une seule source — sinon le logo et l'avatar divergent. Les traits sont donnés **en pixels affichés** : un logo de 16 px n'aurait plus de cerf, un de 256 px en aurait un trop épais |
| `icone.py` | rasterise `hud.icone(trace, n)` **à chaque taille** (16 à 256) — dessiné à cette taille, pas réduit — et assemble `carruos.ico` à la main. Outil de fabrication (Playwright), lancé quand le logo change ; le fichier est livré |
| `majordome.py` | le **compagnon** : le cerf **hologramme** et sa bulle, posés sur **toutes** les pages sauf sa vue complète. Quatre calques animés chacun en entier, aux couleurs du thème |
| | l'onglet MAJORDOME le sort, bulle ouverte, puis le range ; on le déplace par le cerf ou l'entête, **par `transform`**. Position enregistrée en **fraction** de la fenêtre, hors de la `version` du visuel : le déplacer ne repeint rien, mais les autres fenêtres le suivent |
| | son script est **isolé** dans une fonction anonyme (seul `window.CARRUOS_MAJ` sort) ; les commandes propres à l'accueil (`scan`, `toutRafraichir`) ne sont appelées que là où elles existent |
| | le décor de fond est **isolé** (`contain:strict`) et ses tailles sont **plafonnées en pixels** : son coût est proportionnel à la surface, et une taille en `vh` double quand l'écran double |
| `indicators.py` | indicateurs — **PERIODES gelées** |
| `rules.py` | les 13 blocs d'entrée et les 4 sorties |
| `backtest.py` | moteur de simulation, exécution J+1, coûts, **plafond de poids** |
| `phase0.py` | les 5 critères go/no-go |
| `pead.py` | stratégie 2 — **constantes gelées** |
| | J est la **première séance qui peut réagir** : une publication à 16 h ou après (New York) s'échange le lendemain. La lecture littérale prenait la date du calendrier — sur données synthétiques, **0 surprise sur 54** publiées après la clôture passait E2, contre 51 sur 51 maintenant |
| | deux temps : `prepare()` (répétable) relève et **fige** les dates dans un instantané, compte sans rendement sur 2024–2026 et fait une répétition générale sur la période de conception ; `valide()` est le **passage unique** — inscrit au registre avant le calcul, fermé avant l'affichage, refusé la seconde fois |
| | il **ne part pas** sur des données incomplètes (univers tronqué, dates manquantes, heures absentes) : une période de validation brûlée ne se rend pas |
| | le témoin de chaque annonce neutre est simulé **une fois**, puis tiré ; les titres sont parcourus dans l'ordre **alphabétique** — l'ordre d'arrivée des téléchargements parallèles faisait bouger le z au deuxième chiffre |
| | le rapport donne le nombre **réel** de titres par composante, et la période **réellement couverte** (première et dernière publication exploitables), avec les années demandées sans aucune publication |
| | la répétition générale rend un verdict **indicatif** — seul le passage unique juge. Après une répétition NO-GO, le passage ne part plus sur OUI : il faut taper `LANCER QUAND MEME` (`registre.phrase_de_lancement`), et `--valider` ne suffit pas |
| `brain2.py` | **BRAIN 2.0** : le titre et le portefeuille ensemble, sous le contrat du majordome — faits d'abord, prose ensuite |
| | les faits du portefeuille sont **comptés ici** (poids, latent, écart au stop inscrit, stops franchis, lignes sans stop, cours différés, conditions de sortie ligne par ligne) : laissés au modèle, ils seraient invérifiables |
| | le plafond de 25 % ne se vérifie que si **toutes les lignes sont dans une même devise**. Deux lignes en dollars et deux en euros dépassent chacune 25 % « de leur devise » sans rien dire du portefeuille : la première version les signalait toutes |
| | le numéro de compte, l'hôte, le port et le client ne partent **jamais** au fournisseur — deux couches, testées chacune |
| | la page est la **vue complète du majordome**, à `/majordome` (l'ancienne `/brain2` y mène), ouverte depuis la bulle ; la v29 la servait sous `/api/brain2` et aucun onglet n'y menait |
| `registre.py` | le registre des tests, étape 10 du protocole : `~/.carruos/registre-tests.md` pour être lu, `.json` pour refuser un second passage. Aucune ligne n'est jamais réécrite |
| | `autres_regards()` : les passages terminés d'**autres** hypothèses sur une même période — la période se consomme par hypothèse, mais le partage se dit et s'inscrit |
| | `abandonne()` : une hypothèse morte sur sa répétition s'inscrit comme un échec, **sans période** (`PERIODE_ABANDON`) — ce n'est pas un regard sur 2024-2026 — et elle est fermée : `short.bloquants()` refuse ensuite tout passage |
| `short.py` | stratégie 3, vente à découvert — **constantes gelées** |
| | deux temps, comme `pead.py` : `prepare()` (répétable ; comptes sans rendement sur 2024-2026 ; répétition 2010-2023 sur des données **coupées au 31/12/2023**, sinon un trade de décembre se rachèterait sur des cours de 2024) et `valide()`, le passage unique. L'ancienne `lance()`, qui calculait sur la période de validation sans rien inscrire, **n'existe plus** |
| | `bloquants()` : une trace de l'ancienne voie (`short-us.csv`), une période déjà regardée par une **autre** hypothèse (`registre.autres_regards`) ou des documents non validés — ou dont le texte a changé depuis la validation — et rien ne part |
| | S2 (stop) et S4 (thèse morte) se **lisent à la clôture et rachètent à l'ouverture suivante**, au cours réel : le texte dit « le stop sort alors au cours réel d'ouverture ». La première clôture surveillée est celle du jour de la vente ; S1 et S3, connues d'avance, rachètent à la clôture de leur séance. Les moteurs 1 et 2 rachetaient à la clôture même qui déclenchait — la note de lecture de H3 reprenait d'abord cette convention « pour comparer », contre le mot du texte ; corrigé avant validation (point 11) |
| | un GO exige en plus une espérance positive à la ligne « difficile à emprunter », au moins 0,4 point par trade (le dividende non modélisé) et de battre « ne rien faire » net de PFU ; il ouvre six mois d'observation papier. Le témoin est une annonce **sans surprise notable**, ni bonne ni mauvaise. Le biais du survivant n'a pas de sens connu pour une vente, et le rapport ne dit pas « flatté » |
| `decision.py` | **AVANT L'ORDRE** : un achat que le propriétaire envisage — la taille par ses deux règles de risque, le stop mesuré pour ce titre, le calendrier, le marché, ses lignes, et une liste de huit points écrite d'avance ; aucun verdict |
| | le stop par défaut est celui qu'**écrit** la spécification n°1, et la page le dit ; la mesure du stop reprend `recherche.mesure` (périodes non chevauchantes de la durée, gain et perte touchés, Wilson) |
| | enregistrer et inscrire **renvoient les réponses au serveur**, qui recalcule : le carnet (genre `decision`) garde ce que le moteur mesurait, pas ce que la page affichait. La ligne inscrite porte son stop ; une ligne déjà au registre n'est jamais écrasée |
| `comparatif.py` | système contre SMH buy & hold net de PFU |
| `contexte.py` | faits mesurés d'un titre, sans score inventé |
| `chandeliers.py` | 17 figures détectées géométriquement, et ce qu'elles ont été suivies de **sur ce titre** contre son taux de base |
| | les seuils de forme sont écrits **avant** toute mesure et épinglés par `test_moteur` ; les déplacer après coup serait la même pêche que sur les paramètres de stratégie |
| | l'ombre opposée se mesure sur l'**étendue**, pas sur le corps : « ≤ 1 × le corps » exigeait moins de 3 % sur une étoile filante, et le détecteur n'en a jamais trouvé une seule jusqu'à la correction |
| `options.py` | l'open interest des **options** — une action n'en a pas |
| `detention.py` | « si je garde N semaines / mois / ans » : ce que chaque période de cette durée a **donné** sur ce titre, contre l'indice, jamais « la bonne durée » |
| | périodes **non chevauchantes** comptées depuis la fin : vingt ans ne font que quatre périodes de cinq ans, et la carte le dit au lieu d'en inventer mille glissantes |
| | carte SI JE GARDE… de la page graphique (`/api/detention`), intention `detention` du majordome (« je garde 2 mois ? ») |
| `faillites.py` | **RESTRUCTURATIONS** : les 8-K item 1.03 de la SEC regroupés par société, plan confirmé, item 3.03, cours depuis la veille du dépôt, compte complet ; l'Europe à la main |
| | un dépôt compte **une fois** (numéro d'enregistrement), même rendu par son 8-K et ses pièces jointes ; le lien retenu est celui du 8-K. Une simple **mention** de l'item 1.03 sans le déclarer n'est pas une faillite |
| | au-delà de `PAGES_MAX` pages, la réponse porte `tronque` et la page écrit LISTE INCOMPLÈTE : un compte présenté comme complet qui ne l'est pas serait pire que pas de compte |
| | la SEC exige une adresse de contact dans l'en-tête : c'est **celle que le propriétaire tape**, rangée dans `~/.carruos/sec.json`, jamais écrite par le programme — `test_moteur` refuse toute adresse dans le module |
| `recherche.py` | **RECHERCHE** : une somme, un gain visé, une durée, un univers — et pour chaque titre ce que cette durée a **donné**, gain et perte côte à côte |
| | les chemins de toutes les périodes sont une **matrice** (périodes × durée) : une boucle par période coûtait des secondes par univers sur les périodes d'une séance ; `test_moteur` la confronte à une boucle écrite à la main |
| | une recherche à la fois, dans un fil ; la page suit sa progression. L'heure est refusée **avant** tout téléchargement |
| | `ajouts` (tapés) et `detenus` ({ticker: quantité}, `app._lignes_detenues` : registre puis IBKR, IBKR l'emporte) rejoignent l'univers ; l'univers `mes_titres` n'a qu'eux. Les réglages reviennent d'une ouverture à l'autre (`localStorage`, par poste) ; une adresse `/recherche?capital=…&lance=1` les impose — c'est ce qu'écrit le majordome |
| | la **situation** (`chute`, `rebond`, `tendance`, `sommet`) : `masque_situation()` n'utilise que des fenêtres glissantes jusqu'au jour dit — `test_moteur` coupe la série à plusieurs dates et exige le même verdict. Hors situation aujourd'hui, un titre de l'univers sort du tableau et est **compté** ; une ligne détenue reste, marquée. `mesure(..., situation=)` ne prend que des périodes qui **commencent** dans la situation, sans chevauchement (`_bornes_si`) ; `marche()` rend les faits de SPY et ^STOXX, les deux indices du régime |
| `rebond.py` | « rebond ? » : les épisodes de chute ≥ seuil sous le dernier sommet (un par cycle — il faut un **nouveau sommet** pour en ouvrir un autre), et ce qui a suivi à 1, 3, 6, 12 mois contre le taux de base du titre ; Wilson, rien sous 8 épisodes, le biais du survivant écrit à chaque affichage |
| `dossier.py` | la **porte en français** du majordome : une question, une intention, une section de faits |
| | intentions `rebond` (seuil tiré de la question, mesure posée DANS le dossier comme `detention`) et `actualite` (titres d'articles, source, date — **jamais** le ton du fournisseur) ; une question sans titre a sa réponse écrite d'avance (`general`) |
| | intention `marche` (« temps de crise », « tout va bien », « le marché ») : les faits des deux indices posés sous `indices` — `marche` y dit déjà la place du titre, et réutiliser la clé aurait écrasé le choix de l'indice de référence. Il faut des mots de **marché** : « TLX est en crise, rebond ? » reste une question sur le titre |
| | le ticker se tranche par trois dictionnaires, dans l'ordre : les lignes **détenues** (« TLX » quand on détient TLX.DE), la table des noms de `resolve.py` (« Tesla »), puis la cote |
| | aucune phrase n'est *générée*. `constitue()` rassemble ce que les autres modules ont déjà calculé, `intention()` reconnaît ce qui est demandé par une table de motifs écrite d'avance, et les réponses sont des gabarits remplis avec les chiffres du dossier |
| | conséquence tenue **par construction** : si un chiffre n'est pas dans le dossier, aucune phrase ne peut le sortir. `test_moteur` le vérifie en passant un dossier VIDE à chaque section et en exigeant qu'aucun nombre n'en sorte |
| | quel mot est un ticker se tranche **côté serveur, en interrogeant les données** : « QUE PENSE TU DE TLX » ne donne aucun autre indice |
| `palmares.py` | **MA LISTE** : des titres collés à la main, passés aux 13 blocs, groupés et triés |
| | un jeton à points multiples (`COIN.HOOD.MC.PA`) est découpé en **demandant aux données** si chaque morceau existe, jamais par une règle syntaxique : `.MC` est le suffixe de Madrid, donc `HOOD.MC` est plausible alors que le lecteur voulait `HOOD` puis `MC.PA`. C'est un découpage de mots résolu par le dictionnaire |
| | aucun score composite : le tri par défaut est celui de la spécification, les autres portent sur un fait unique |
| `interet.py` | la carte INTÉRÊT : quatre comptes, une échelle de 7 marches |
| | le verdict de la page graphique en **découle** au lieu d'être calculé à côté : deux échelles parallèles finissent par se contredire |
| | et cette échelle regarde les **vetos**, ce que l'ancienne ne faisait pas — un titre à 13/13 dont le volume dollar est sous le plancher s'affichait ACHAT, entrée, stop et nombre de titres compris |
| | le vocabulaire suit l'unité de temps : « la veille » est faux sur l'onglet 1 MOIS, et le génitif se contracte |
| `positions.py` | registre manuel des positions |
| | `controle()` rend un **état compté** — sous le stop inscrit, ou « n conditions de sortie actives sur 4 » — et `RAPPEL_ETAT` : la spécification ferme à la première. Il rendait CONSERVER / SURVEILLER / SORTIE, affiché sous « VERDICT » dans MES POSITIONS de l'accueil, deux versions après que `portefeuille.py` eut perdu le même verdict |
| | chaque ligne porte sa **devise de cotation** (déduite du suffixe de place) et un **contrôle de cohérence** du prix d'entrée : s'il n'est jamais tombé dans l'intervalle parcouru par le titre, la carte le dit et prévient que le gain latent affiché est faux |
| `news.py` | Alpha Vantage — quota 25/jour, caches obligatoires |
| | `ton()` : l'**étiquette** du fournisseur (positif … négatif), traduite mot pour mot et attribuée à l'écran ; rien ne s'en sert |
| | la clé est rangée **deux fois** : `.bruce_cache` à côté du programme, et `~/.carruos/` — cette seconde copie est la seule qui survive à une mise à jour, `.bruce_cache` n'étant pas livré dans l'archive |
| | `app.retrouve_cle()` va la chercher dans une installation **voisine** si les deux manquent. Portée volontairement étroite : un seul niveau au-dessus du programme plus quelques dossiers usuels, deux niveaux de profondeur, plafond de 400 dossiers, un seul nom de fichier lu. Elle ne tourne **jamais** si `~/.carruos/` existe déjà — sinon effacer volontairement la clé la ferait ressusciter au lancement suivant |
| | **aucune clé ne doit entrer dans le dépôt.** `.bruce_cache/` est ignoré et `test_pages` refuse tout jeton de 16 majuscules dans un fichier suivi par git |
| `data.py` | chargement yfinance, 8 univers, compositions figées |
| | les univers composés (`us`, `us_total`) se chargent **composante par composante** (`univers_detaille`) : chaque liste a ses adresses et un minimum de lignes, la dernière liste réussie est gardée datée, un échec se replie sur elle **en affichant sa date**, et sans elle c'est l'arrêt (`UniversIndisponible`). Jamais un univers amputé sous l'étiquette de l'univers complet. `--figer` refuse un repli, qui porterait la date du jour sans en être la composition |
| | `annees_de_cours(debut)` : la profondeur des cours se calcule depuis le début de la période de conception, 260 séances de préchauffage comprises, et non plus en années fixes |
| `cache.py` | cache disque et téléchargements parallèles |
| `qualite.py` | refus de signal sur données douteuses |
| `audit.py` | journal des signaux, empreinte des paramètres |
| `robuste.py` | stabilité, Monte Carlo, bootstrap par blocs |
| `calibration.py` | met le critère 4 à l'épreuve sur du bruit pur |
| `horizon.py` | amplitude par horizon, objectif atteignable, entrée en euros |
| `seance.py` | horaires des 9 places, fériés **calculés**, heure d'été suivie |
| `strategie.py` | projection de réinvestissement, revue de ligne |
| | la projection sépare **ce que vous versez** de **ce que le fonds capitalise tout seul**, année par année, et donne l'année où le second dépasse le premier |
| `cerveau.py` | le modèle de langage du majordome, **sous contrat vérifié** |
| | les faits d'abord, la prose ensuite ; le modèle ne voit jamais les cours ; chaque nombre de sa réponse est confronté au dossier envoyé et ceux qui n'y sont pas sont **nommés** à l'écran |
| | le dossier trop lourd est **réduit, jamais coupé** (`compacte`) : listes ramenées à 12, 6 puis 3 éléments, puis sections lourdes retirées **en le disant** (`_omis`). Les sections protégées ne sont ni retirées ni raccourcies. Les chiffres se vérifient contre ce qui a été **envoyé** |
| | recherche Web chez **les deux** fournisseurs (la v29 ne l'avait branchée que pour OpenAI, alors que le fournisseur par défaut est Anthropic) ; sources rendues **à part** du texte ; un modèle qui refuse l'outil répond sans lui |
| | un refus du fournisseur est **dit en français avec ce qu'il faut faire** (`explique_erreur`) : compte sans crédit, clé refusée, quota, surcharge. Un refus **définitif** (crédit, clé) ne fait plus reposer la question sans l'outil. La clé est **essayée au moment de BRANCHER** (`essai()`, quelques dizaines de jetons) |
| | clés : celles de CARRUOS d'abord, les variables génériques (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) en dernier recours — la v29 laissait la générique écraser la spécifique. Une clé d'environnement n'est jamais écrite sur le disque |
| | la tolérance de cette comparaison vaut une **demi-unité du dernier chiffre écrit** : « 12 % » peut venir de 11,83 %, « 11,8 % » ne peut venir que d'entre 11,75 et 11,85. Une première version arrondissait les deux côtés à zéro décimale — 0,38 et 0,62 s'écrasaient sur 0 et 1, et « 73 % » tombait sur le même 1 que 0,62. Le contrôle validait un chiffre inventé |
| `profil.py` | ce qui distingue une action d'un ETF monde, **mesuré** |
| | la durée de détention n'est pas déclarée, elle est **rejouée** : les règles de la spécification tournent sur tout l'historique et on relève la durée des trades obtenus |
| `objectif.py` | une cible chiffrée, résolue par l'arithmétique, jamais refusée |
| `carnet.py` | vos notes, et des relevés datés de ce que le moteur mesurait |
| `ibkr.py` | le compte IBKR en direct, **en lecture seule par construction**, et la seule porte du programme vers IBKR |
| | un fil d'exécution possède la session et sa boucle d'événements ; les pages ne lisent qu'une **photo** sous verrou. TWS se relance une fois par jour : la liaison se reconnecte seule, avec une attente croissante |
| | un contrat IBKR devient un ticker CARRUOS par une table de places **écrite d'avance**. Une place absente ne se devine pas : la ligne garde son nom IBKR et le dit, plutôt que d'ouvrir le graphique d'un autre titre |
| | le stop comparé au cours est celui **inscrit dans le registre**, jamais un stop calculé ; le franchissement est un fait, et le type du cours voyage avec |
| | `hote_valide` : l'adresse de TWS est une IP, `localhost` ou un nom à points — un mot seul (« U1234567 », un numéro de compte) redevient 127.0.0.1, à la saisie **et** à la relecture |
| | se brancher, c'est répondre à **deux questions** — quel logiciel, quel compte — dont le port **découle** (`PORT_DE`, table unique que la page reprend du serveur). `detecte()` frappe aux quatre ports de la **boucle locale** seulement, par une ouverture TCP refermée aussitôt : aucun échange avec l'API. Aucun identifiant n'est demandé, et la page le dit |
| | `ibkr.FABRIQUE` remplace la bibliothèque pour les tests — même procédé que `data.load_yf` : un faux TWS, sans réseau |
| `portefeuille.py` | le même compte en ligne de commande, **par `ibkr.py`**. Il avait sa propre porte, une table de places qui retombait sur un ticker américain pour toute place inconnue, et un verdict CONSERVER / SURVEILLER / SORTIE ; il rend maintenant le compte des conditions de sortie actives |
| `veille.py` | rapproche l'actualité de vos lignes — une **jointure**, jamais une analyse |
| | trois niveaux de force, étiquetés : nommé par la source, même secteur déclaré, mot trouvé dans le titre. À l'écran, le plein et le pointillé les distinguent sans légende |
| | la table thème → secteur est délibérément **pauvre** : chaque maillon ajouté serait une supposition. Les thèmes macro ne pointent vers rien, parce qu'ils concernent tout le marché |
| `memoire.py` | ce que le programme a dit, et ce qui a suivi : le **compte complet**, jamais le regret sélectif |
| | horizons **écrits d'avance** (5, 20, 60 séances), écart au marché (SPY ou ^STOXX selon la place) ; une même barre relevée deux fois ne compte qu'une fois, et un même titre ne donne qu'**une observation par fenêtre** de l'horizon |
| | un verdict (« filtre utile » / « nuisible ») seulement si **deux** mesures de l'incertitude l'accordent : non-recouvrement des Wilson, et bootstrap qui tire les **titres**. Sur du bruit, le bootstrap seul rend 5,5 à 8,5 % de faux verdicts, la règle moins de 1 % ; `test_moteur` le remesure |
| | vos achats IBKR rangés **avec** ou **contre** le signal — seulement si un état a été relevé au plus 5 jours **avant** l'ordre. Jamais reconstitué après coup : ce serait juger avec un regard qui connaît la suite |
| | chaque exécution consignée fait relever l'état **à la clôture de la veille** de l'ordre (`app._releve_etat(avant=…)`), séries coupées avant le jour de l'ordre : la spécification décide à la clôture et exécute à l'ouverture suivante. `test_moteur` vérifie que rien du jour même n'y entre |
| | chaque ouverture d'une page graphique écrit son état au journal (fil de fond) : c'est ce qui nourrit la mémoire, titre après titre |
| `reglages.py` | **13 thèmes**, 13 effets visuels débrayables |
| | `visuel()` : l'apparence **complète** (variables, classes de `<body>`) et sa `version`. Chaque page ouverte la compare à la sienne au retour du focus et toutes les 4 s, et reprend tout si elle a changé — un thème choisi dans une fenêtre repeint les autres |
| | un thème porte une `forme` : biseau, arrondi, équerres, densité, matière, typographie. Les valeurs par défaut **sont** l'apparence d'origine, donc un thème qui n'en redéfinit aucune ne change rien |
| | **aucun thème clair** : ce n'est pas au goût du propriétaire, et `test_pages` le vérifie |
| | **fluidité** : `auto` mesure la cadence réelle sur la machine de l'utilisateur et passe le décor en mode sobre si elle ne suit pas — puis **recommence à chaque redimensionnement**, parce que c'est là que le problème apparaît. `complet` et `sobre` tranchent à la main, et la mesure ne revient jamais sur un choix explicite |

## Chantiers

1. **Univers historiques** — *outillé, à alimenter.*
   `data.figer_univers()` enregistre la composition du jour, datée, dans
   `~/.carruos/univers` — pas dans `.bruce_cache`, qui n'est pas livré et
   qu'une mise à jour dans un nouveau dossier laissait derrière elle ;
   l'ancien dossier reste lu. `univers_a_la_date()` relit la plus proche
   avant une date donnée.
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
- **Une animation ne doit toucher qu'à `transform` et `opacity` — et le
  test part d'une liste BLANCHE.** L'ancienne version énumérait les
  propriétés interdites à la main (`top`, `left`, `width`, `height`,
  `margin`, `padding`, `background-position`). Elle a laissé passer
  `letter-spacing` et `text-indent` dans l'animation du titre
  d'ouverture : sur un titre centré, le mot se recalcule à chaque image
  et **toute la ligne se déplace de 46 px**, d'autant plus visible que
  l'écran est grand. C'était le « visuel qui saute » de la première
  page. Le même effet se fait lettre par lettre en `transform` : la
  largeur du mot ne change plus jamais. Une liste d'interdits oublie
  toujours quelque chose ; une liste d'autorisés ne peut rien laisser
  passer en silence. Le contrôle porte sur les **trois** pages, pas
  seulement l'accueil.
- **Le décor coûte cher, et son coût suit la SURFACE de la fenêtre.**
  Mesuré : 152 ms par image en 1420 de large, 345 ms en 2560 — deux
  fois pire en plein écran. Le cerf est tracé **cinq fois** et mis à
  l'échelle à chaque image (61 % du temps), cinq anneaux tournent
  (41 %). On ne devine pas la machine de l'utilisateur : on la mesure,
  et le décor se calme tout seul si elle ne suit pas. `contain:strict`
  sur `.fond` divise le temps par image par deux et n'a **aucun** effet
  visible — cela se démontre plutôt que de s'espérer : `paint` est
  redondant avec le découpage déjà en place, `layout` l'est parce que
  tous les enfants sont absolus, `style` ne concerne que compteurs et
  guillemets, `size` parce que la taille vient de `inset:0`.
- **Une comparaison de type qui ne tombe jamais ne se voit pas.**
  `_bloc_etats` rend `'ok'` / `'ko'` / `'na'`, des **chaînes**. Le script
  de la page les comparait à `1` et à `true` : le compteur rendait donc
  toujours zéro, le cercle central restait vide et la voix annonçait
  « 0 blocs sur 13 » sur un titre qui les avait tous. Rien ne plantait.
  Dans la même fonction, la table de couleurs était indexée sur `sortie`
  alors que le verdict vaut `vente` : l'anneau retombait sur le gris au
  moment précis où il devait alerter. `test_pages` vérifie maintenant que
  **chaque état possible a sa couleur et sa classe CSS**, en partant de la
  table Python — pas d'une liste recopiée à la main.
- **Un test peut valider une mécanique et rater ce qu'elle produit.** Le
  test du repli vérifiait que la fonction était définie avant la balise —
  elle l'était — sans jamais vérifier que la bibliothèque finissait par
  être là. Vérifier le résultat, pas le montage.
- **Une classe produite sans règle CSS ne plante pas : elle s'affiche
  en texte brut.** `.mods`, `.mod`, `.hdr2`, `.gg`, `.zone`, `.val`,
  `.nw2` n'étaient définis **nulle part**. Le bandeau du bas de la page
  graphique s'affichait donc empilé, libellés collés aux chiffres —
  « 57RSI 14 zone 40-55 » — pendant que le reste de la page était
  soigné. Les deux seules règles existantes, `.pil-l .mod` et
  `.pil-l .kv`, surchargeaient du vide. `test_pages` **relève** les
  classes que `_modules` produit réellement et exige que chacune
  apparaisse dans la feuille : aucune liste écrite à la main, donc un
  module ajouté demain avec une classe nouvelle fait tomber le test.
- **Une grille pose sa largeur d'après son CONTENEUR, pas d'après la
  fenêtre.** `.hud-g` était en `1fr auto 1fr` avec un repli en
  `@media(max-width:900px)`. Ce bandeau est posé dans la colonne gauche
  de la page graphique, large de 190 px : sur un écran de 1920 la
  requête ne se déclenchait jamais, les pistes prenaient 332 px et
  208 px dans une boîte de 192, et **le panneau des seuils et les rails
  partaient entièrement hors champ**, cachés par le défilement. Sans
  rien qui le signale. `repeat(auto-fit, minmax(min(100%,190px),1fr))`
  n'a besoin d'aucune requête. Et `min-width:0` sur les enfants : sans
  lui, un enfant de grille refuse de descendre sous la taille minimale
  de son contenu et déborde sa piste en silence.
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
  décalait toute la grille. Elle est désormais en
  `clamp(78px,44%,128px)` — la largeur ne dépend que du **conteneur**,
  jamais du contenu — et `tabular-nums` sur les chiffres pour que `0/5`
  et `12/5` occupent la même place. Le test vérifie la **propriété**
  (aucune piste en `auto`/`min-content`/`max-content`/`fit-content`) et
  non plus la chaîne exacte `128px 1fr 62px` : un test qui exige la
  lettre d'un correctif refuse une bonne solution écrite autrement et
  laisse passer une mauvaise écrite avec les mêmes chiffres.
- Toute animation CSS doit porter sur `transform` ou `opacity`. Animer
  `top`, `left`, `width` ou `background-position` fait sauter la page
  entière. `test_pages` le vérifie.
- **Un nom de classe par intention, et jamais celui d'une carte dans la
  barre.** L'horloge portait `class="etat"` — le nom déjà pris par une
  CARTE de l'accueil, qui vaut marge 10/12 px, écart intérieur 13 px et
  une bordure. `.bar .etat` ne surchargeait que la police, donc la barre
  héritait de la boîte d'une carte : **61 px de haut au lieu de 30**, et
  ces 31 px étaient pris à la grille de contenu à chaque ouverture de
  page. C'est le « mal dimensionné » signalé, et rien dans le rendu ne
  le disait. `test_pages` compare les classes posées **dans** la barre à
  celles posées ailleurs, et ne retient que les noms qu'une règle **sans
  ancêtre** atteint des deux côtés — sans cette nuance il refuserait des
  noms qui ne se rencontrent jamais, et un test qui crie pour rien finit
  par ne plus être lu.
- **Une règle CSS posée dans la feuille d'une AUTRE page ne s'applique
  nulle part, et la page se dessine quand même.** `.app.crn-page` avait
  atterri dans `CSS_STRAT`, que la page CARNET ne charge pas : les deux
  panneaux se calaient sur leur contenu et un tiers de l'écran restait
  vide sous eux. `test_pages` compare désormais, pour chaque page, les
  classes de sa **coquille** (`<body>` et `.app`) aux règles de **sa**
  feuille. Les classes `theme-…` en sont exemptées : un thème qui ne
  redéfinit rien n'a légitimement aucune règle. Le même défaut vivait **un cran
  plus bas** : `.ex`, `.bilan` et `.titre-sec` n'étaient réglés que
  dans la feuille de STRATÉGIE, et cinq autres pages les posaient — en
  14 px sans marge ; le cerf de la barre prenait sa couleur dans la
  feuille de l'accueil, et la page graphique le peignait en **noir sur
  noir**. `test_pages` relève maintenant toutes les classes qu'une page
  pose, HTML **et** scripts, et refuse celles qui ne sont réglées que
  dans la feuille d'une autre. Une classe réglée nulle part reste
  permise : c'est un crochet de script, pas un oubli.
- **Un bloc unique sous la barre tombe dans une ligne `auto`.** `.app`
  est une grille de 100vh en `auto auto minmax(0,1fr)` sous
  `body{overflow:hidden}`. MA LISTE n'y posait qu'un bloc : il allait
  dans la deuxième ligne, `auto`, s'allongeait sous le bas de l'écran,
  et la molette ne l'atteignait plus — une liste de quarante titres
  était coupée depuis la création de la page, sans rien qui le dise.
  Vu au rendu de RESTRUCTURATIONS, qui avait le même défaut. Une page
  d'un seul bloc porte `une-zone` et son contenu va dans `.defile`.
  `test_pages` regarde **chaque** page : si `.app` n'a que la barre et
  un bloc, sa coquille doit redéfinir les lignes.
- **Un texte sous un petit graphique le réduit à zéro.** La bande des
  bougies avait sa phrase en dessous, sur trois lignes, et son axe du
  temps : dans une rangée de 80 px, il restait 0 px au tracé. Le rendu ne
  plantait pas, la bande était simplement vide. Le texte est posé SUR la
  bande, l'axe du temps retiré (les dates se lisent sous le prix, aligné),
  et une largeur minimale commune aux échelles de droite garde les dates
  des quatre graphiques au même endroit. Et le premier essai de survol
  ne donnait rien parce qu'il visait l'axe du temps, pas le tracé :
  regarder où l'on clique avant de conclure que l'événement ne part pas.
- **Un bouton sous le pli d'un panneau qui défile n'existe pas.**
  RECHERCHE et RESTRUCTURATIONS avaient été posés en BAS des scans
  complets : à 1 420 px, la taille de la fenêtre, le panneau s'arrêtait
  à 917 px et le bouton commençait à 948. « Je ne vois pas le bouton
  RECHERCHE. » Les deux outils sont en tête du panneau, et les scans sur
  plusieurs colonnes ; `test_pages` exige que RECHERCHE vienne avant le
  premier scan. Un test qui vérifie qu'un bouton est DANS la page ne dit
  pas qu'on le VOIT.
- **Un verdict retiré à un endroit survit à un autre.** `portefeuille.py`
  avait perdu CONSERVER / SURVEILLER / SORTIE ; `positions.controle()`
  les produisait toujours, et l'accueil les affichait sous « VERDICT ».
  Chercher le mot dans tout le code, pas dans le module qu'on corrige.
- **Un mot de la question peut en déclencher une autre.** « Tesla va
  sortir un nouveau modèle » tombait sur l'intention SORTIE, à cause de
  « sortir » : le majordome répondait VOUS SORTEZ QUAND à une question
  sur une annonce. L'ordre de la table compte — l'intention précise avant
  la générale — et `test_moteur` épingle les deux phrases.
- **Des données qui acceptent tout font de chaque mot un ticker.** Sur
  les séries d'essai, « des ACTIONS en chute libre » donnait le titre
  « ACTIONS ». Les mots des questions générales sont dans `MOTS_VIDES`,
  et le test passe une fonction `existe` qui dit oui à tout.
- **Le script du compagnon est sur toutes les pages, ses mots aussi.**
  La clé de situation `haussiere`, écrite dans le majordome, a fait
  tomber le contrôle « aucun HAUSSIER » de la page STRATÉGIE — qui ne
  parle pas de recherche. Le contrôle avait raison sur le fond : le mot
  est un mot de direction. La situation s'appelle `tendance` et se
  définit par ses faits.
- **Une convention reprise « pour comparer » peut contredire le texte.**
  La note de lecture de H3 gardait le rachat du stop à la clôture qui le
  déclenche, comme aux hypothèses 1 et 2, en la déclarant optimiste. Le
  texte de H3 écrit « le stop sort alors au cours réel d'**ouverture** ».
  Relue avant toute validation, la note suit le texte : lu à la clôture,
  racheté à l'ouverture suivante — la même séparation qu'à l'entrée. Une
  lecture se juge contre la spécification qu'elle lit, pas contre les
  moteurs précédents.
- **Une idée de correction se vérifie contre le critère qu'elle doit
  faire passer.** Après la répétition de H3, j'ai proposé de « couvrir le
  marché » — vendre le titre, acheter l'indice. Le critère qui tombait
  était le z contre les annonces **sans surprise** ; la couverture retire
  la hausse du marché au trade ET au témoin, et le z reste près de zéro.
  C'est écrit dans `pistes-2027-BROUILLON.md` pour ne pas être repris.
- **Une clé de dossier se vérifie avant d'être prise.** Les faits du
  marché, posés d'abord sous `marche`, écrasaient la place du titre
  (`us` / `europe`) que le dossier range sous ce nom et dont dépend
  l'indice de référence. Ils sont sous `indices`.
- **Une grille dimensionne ses enfants par ses lignes EXPLICITES.**
  Ajouter un panneau à une grille qui n'en déclarait qu'une envoie le
  nouveau dans une ligne implicite calée sur son contenu. Sur la page
  STRATEGIE, MES LIGNES partait ainsi sous le pli — et
  `body{overflow:hidden}` le rendait **inatteignable**, pas seulement
  mal placé.
- **Un `except` muet efface une carte sans un mot.** La carte PROFIL
  cherchait la série dans `data["jour"]`, qui porte les tableaux déjà
  mis en forme pour le navigateur et non la colonne `close`.
  L'exception tombait dans le `except` et la carte disparaissait en
  silence. Le `except` trace, et le test regarde ce que la page
  **produit** — la charge, ses lignes, son rappel — au lieu de se
  contenter de voir la fonction définie.
- **Une page absente du test n'a aucun défaut.** CARNET n'était pas
  dans la liste de `test_pages`, donc ni son script mort ni sa grille
  de travers ne pouvaient être vus. Toute page servie entre dans la
  liste.
- **Couper un texte au caractère près fait tomber sa FIN.** Le dossier
  envoyé au modèle était tronqué à 24 000 caractères par une tranche de
  chaîne. Un dossier de titre ordinaire en fait 32 000 : le profil, la
  mémoire et la position détenue — posés en dernier — n'ont jamais été
  vus par le modèle. Dans BRAIN 2.0 (70 000 caractères), c'était le
  portefeuille entier, c'est-à-dire la raison d'être de la page. Et la
  vérification des chiffres se faisait contre le dossier complet : une
  valeur jamais envoyée « justifiait » un chiffre écrit. Réduire par
  structure, protéger ce qui compte, dire ce qui manque, vérifier contre
  ce qui est parti.
- **Une page que rien n'ouvre n'existe pas.** La v29 annonçait « le
  bouton BRAIN 2.0 ajouté au logiciel » et l'adresse `/brain2` : ni l'un
  ni l'autre n'existaient. Les trois suites passaient, parce que la page
  n'était dans aucune. Elle y est, et le test vérifie que la barre y mène.
- **Une fenêtre fille sans `js_api` n'a pas de pont vers Python.** Les
  onglets ouverts depuis une fenêtre fille passaient donc par
  `window.open`, c'est-à-dire par le **navigateur** : « des fenêtres
  locales pour tous les onglets » ne tenait que depuis l'accueil. Et le
  pont arrive un instant **après** la page : `ouvreFenetre` attend
  `pywebviewready` (2 s au plus) avant de se rabattre.
- **Une icône posée une fois ne l'est que sur une fenêtre.** `WM_SETICON`
  vise un handle : le logo n'était posé que sur la première, les fenêtres
  filles gardaient celui de Python. Une veille les reprend au fil de leur
  ouverture.
- **Un réglage appliqué à la page qui le change ne l'est pas aux autres.**
  Le serveur rendait bien chaque **nouvelle** page au bon thème ; une
  fenêtre déjà ouverte ne l'apprenait jamais, et même la page où l'on
  choisissait n'appliquait que six couleurs sur vingt-six variables.
  Comparer une version, reprendre tout.
- **Une fonction qui n'existe que sur une page.** Le majordome vivait dans
  le script de l'accueil : aucune autre fenêtre n'en avait, et ses
  commandes appelaient `scan()` ou `go()` sans se demander si elles
  existaient. Un module, posé partout, et un `typeof` devant tout ce qui
  appartient à une seule page. `test_pages` exige le compagnon sur
  chaque page servie.
- **Un message d'erreur doit dire quoi faire.** « anthropic a répondu 400 :
  {"type":"error",…"credit balance is too low"…} » : la clé était bonne,
  c'est le compte API qui n'avait pas de crédit — et l'abonnement Claude
  n'en donne pas. Rien ne le disait, et le programme reposait la question
  une seconde fois, comme si l'outil de recherche était en cause. Un refus
  se traduit, et un refus définitif ne se repose pas.
- **Une règle CSS sur `svg` descend dans les `<svg>` imbriqués.**
  `.mj-a svg{width:100%;height:100%}` visait les calques de l'avatar et
  étirait aussi le cerf, un `<svg>` placé par ses attributs x/y : il
  débordait du médaillon. `.mj-a>svg`. Et un serveur d'essai lancé
  **avant** une correction sert l'ancien code : relancer avant de regarder.
- **Une icône posée par-dessus peut être reprise.** pywebview (WinForms)
  crée chaque fenêtre avec l'icône de `pythonw.exe` et la réapplique ; le
  `WM_SETICON` envoyé une seule fois par fenêtre ne tenait pas, et la
  fenêtre IBKR montrait le logo Python. L'icône se pose là où WinForms la
  garde — la propriété `Icon` de la fenêtre, sur son fil — et la veille
  regarde l'icône **actuelle** au lieu de se souvenir qu'elle l'avait
  posée. Le test simule la fenêtre et .NET et regarde le résultat.
- **Une saisie fausse enregistrée échoue à chaque lancement.** Un numéro
  de référence tapé dans la case « adresse » de l'ancienne page était
  relu à chaque connexion : « getaddrinfo failed », toutes les 60 s. La
  valeur se valide à la saisie **et** à la relecture.
- **Un raccourci vers un `.vbs` dépend d'une association de fichier.**
  Sur un PC où les `.vbs` s'ouvrent dans le Bloc-notes, il ouvre le
  script au lieu de lancer le programme. Le raccourci vise `wscript.exe`.
  Et Windows garde les icônes en cache sous le **nom** de leur fichier :
  la copie de l'icône porte sa taille dans son nom.
- **Trois cases sans dire laquelle compte, c'est une question de
  trop.** L'onglet IBKR demandait une adresse, un port et un « numéro de
  client » : « avec quel numéro de référence je dois rentrer ? ». Un seul
  compte — le port — et il se **déduit** de deux choix que l'utilisateur
  connaît (TWS ou Gateway, simulation ou réel). Les deux autres sont
  rangés dans « réglages avancés », avec ce qu'ils ne sont pas.
- **Un `.bat` en fins de ligne Unix** fait rater des `goto` à `cmd.exe`
  quand une étiquette tombe à cheval sur son tampon de 512 octets.
  `Carruos.bat` était le seul de sa famille dans ce cas ; `test_pages`
  vérifie maintenant chaque `.bat` et `.vbs`.
- **Un septième onglet a fait repasser la barre sur deux lignes** à
  1 180 px (48 px au lieu de 30). En dessous de 1 300 px, la date et
  « PARIS » s'effacent de l'horloge, puis le sous-titre sous 1 120 px : la
  barre tient sur une ligne de 1 000 à 1 400 px, mieux qu'avant.
- **Un moteur peut respecter ses constantes et trahir son texte.**
  L'empreinte de `pead.py` couvrait les seuils, pas leur lecture. Le
  moteur prenait la date du calendrier pour « jour d'annonce » : toute
  publication après la clôture voyait son volume mesuré la veille de la
  réaction, et E3 ne vérifiait plus rien. Rien ne le signalait, et le
  passage unique serait parti avec. Relire un moteur **contre le texte**,
  ligne à ligne, avant de dépenser une période de validation — et
  inscrire au registre l'empreinte du **code** qui a tourné, pas
  seulement celle des constantes.
- **Un résultat inscrit au registre doit se reproduire.** Le z tiré au
  hasard dépendait de l'ordre des titres, donc de l'ordre d'arrivée des
  téléchargements parallèles. Trier avant de tirer.
- **Une explication plausible n'est pas une mesure.** Un premier journal
  d'essai a rendu « filtre nuisible » sur des données au hasard. J'y ai
  vu l'effet du regroupement par titre, je l'ai écrit, et j'ai codé le
  bootstrap par titres pour le corriger. La mesure sur 200 journaux de
  bruit a dit autre chose : le critère d'origine ne se trompait que
  dans 0,5 à 2,5 % des cas, et c'est le nouveau qui en rendait le plus.
  Le « nuisible » était un tirage malchanceux. La règle retenue exige
  que les deux s'accordent, sur le modèle de `phase0.z_retenu()` : elle
  ne peut que rendre moins de verdicts. Mesurer d'abord, expliquer
  ensuite.
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
