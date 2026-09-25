# CARRUOS ALICE — le majordome

## Le faire apparaître

L'onglet **MAJORDOME** de la barre, sur toutes les pages. Un clic : le
cerf du logo apparaît, bulle ouverte. Bulle ouverte, un second clic le
range. Toutes les fenêtres ouvertes suivent.

- **Cliquer le cerf** ouvre ou ferme la bulle ; **Échap** la ferme.
- **Le déplacer** : le prendre par le cerf ou par l'entête de la bulle,
  et le poser où l'on veut. La place est retenue, en proportion de la
  fenêtre : les autres fenêtres le posent au même endroit, et une
  fenêtre plus petite ne l'envoie pas hors champ.
- **RANGER** le fait disparaître partout ; l'onglet le rappelle.
- **VUE COMPLÈTE** ouvre sa page entière (adresse `/majordome`).

Sur une page graphique, il parle du titre affiché quand la question
n'en nomme aucun ; sur l'accueil, du titre écrit dans « analyser un
titre ».

## Ce qu'on peut lui demander

« je sors quand sur TLX », « combien je peux perdre sur Coin », « que
penses-tu de Nvidia », « une figure sur Hood ? », « on garde TLX combien
de temps », « ouvre Sanofi », « scan cac 40 » (lancé depuis l'accueil),
« état du marché », « mes positions », « la veille sur mes lignes ».

## La vue complète

**À gauche, les faits**, calculés par le programme **avant** tout appel au
modèle, et affichés quoi qu'il arrive — clé absente, service en panne,
réponse de travers :

- la fiche du titre qui répond à la question (« je garde ? » : les quatre
  conditions de sortie ; « que penses-tu de… ? » : les 13 blocs) ;
- ce que le titre bouge par horizon, **sans direction** ;
- combien de temps la spécification a réellement tenu ce titre — la durée
  de détention est une conséquence des règles de sortie, pas un choix ;
- vos lignes, **comptées** : poids, gain latent, écart au stop inscrit,
  stops franchis, lignes sans stop, cours qui ne sont pas en temps réel,
  conditions de sortie actives ligne par ligne.

Le portefeuille est celui du compte IBKR s'il est branché (lecture seule),
sinon celui du registre local des positions.

**À droite, le cerveau** : le modèle de langage met ces faits en phrases.
Il peut chercher sur le Web ; ses sources sont listées sous sa réponse.
Chaque chiffre qu'il écrit est confronté au dossier qu'il a reçu, et ceux
qui n'en viennent pas sont **nommés**. La conversation se poursuit : les
échanges précédents lui sont renvoyés.

## Ce que le majordome ne fait pas

Il ne dit ni « achète », ni « vends », ni « garde ». Quand on le lui
demande, il répond comme un mentor : ce qui est mesuré, ce que la
spécification ferait (elle ferme à la **première** condition de sortie
atteinte), ce qui manque pour juger, ce qui changerait le tableau, et les
questions à se poser. Aucune hypothèse de CARRUOS n'a passé sa
validation : un avis directionnel serait une opinion déguisée en mesure.

Il ne voit jamais les cours, n'invente aucun chiffre, ne prédit aucun prix,
ne choisit pas un « meilleur horizon ».

## Ce qui part chez le fournisseur du modèle

La question, les faits du titre, les faits du portefeuille. **Jamais** le
numéro de compte IBKR, l'hôte, le port ni le numéro de client — un test le
vérifie. Le dossier est plafonné ; s'il est trop lourd, il est réduit sans
être coupé, le portefeuille passe en premier, et ce qui n'a pas pu être
envoyé est signalé à l'écran.

## Les clés

Celle que vous saisissez dans la bulle (« CERVEAU », en bas), rangée dans
votre profil Windows. À défaut, les variables `CARRUOS_ANTHROPIC_API_KEY` /
`CARRUOS_OPENAI_API_KEY`, puis — en dernier recours seulement —
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. La bulle dit d'où vient la clé
utilisée. Une clé venue d'une variable d'environnement n'est jamais écrite
sur le disque.
