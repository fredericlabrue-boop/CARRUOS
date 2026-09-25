# CARRUOS BRAIN 2.0

## Ouvrir

L'onglet **BRAIN 2.0** de la barre, sur toutes les pages (adresse
`/brain2`). Un titre et une question — ou rien que la question : sans
titre, c'est le portefeuille qui est analysé.

## Ce que la page montre, dans cet ordre

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

## Ce que le cerveau ne fait pas

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

Celle que vous saisissez dans le majordome, rangée dans votre profil
Windows. À défaut, les variables `CARRUOS_ANTHROPIC_API_KEY` /
`CARRUOS_OPENAI_API_KEY`, puis — en dernier recours seulement —
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. La page dit d'où vient la clé
utilisée. Une clé venue d'une variable d'environnement n'est jamais écrite
sur le disque.
