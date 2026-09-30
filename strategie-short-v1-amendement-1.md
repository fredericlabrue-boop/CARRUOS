# DÉRIVE POST-ANNONCE NÉGATIVE v1.0 — AMENDEMENT N°1 : LA PÉRIODE DE VALIDATION
### Proposé le 30 septembre 2026, **avant** tout regard de l'hypothèse n°3 sur 2024–2026
### Statut : **proposition**. Il ne vaut qu'une fois validé par le propriétaire.

La validation se fait sur la machine du propriétaire :

    py -m equity_scanner.short --valider-documents

Elle est datée, liée à l'empreinte SHA256 de ce texte et de la note de
lecture, et le passage unique la vérifie. Si l'un des deux textes change
après la validation, elle ne vaut plus.

---

## 1. Ce qui est devenu faux

L'étape 4 de la spécification écrit :

> La période de validation est celle de l'hypothèse n°2, **qui n'a pas
> encore été consommée**. Elle n'a jamais servi à régler quoi que ce soit.

La première phrase est fausse depuis le **29 septembre 2026, 21 h 03** :
l'hypothèse n°2 a fait son passage unique sur 2024–2026, NO-GO, inscrit
au registre. Le texte de la spécification ne se retouche pas ; cet
amendement dit ce qu'il faut en conclure, et il le dit avant que
l'hypothèse n°3 ait regardé quoi que ce soit.

## 2. Ce que dit le protocole

Étape 3 : « Une fois qu'on l'a regardée, elle est brûlée **pour cette
hypothèse** : tout ajustement ultérieur testé dessus est contaminé. »

La période se consomme **par hypothèse**. Ce qu'elle protège, c'est
qu'aucune règle n'ait été réglée en connaissant le résultat. La seconde
phrase de l'étape 4 — « elle n'a jamais servi à régler quoi que ce
soit » — est donc celle qui compte, et elle reste vraie :

- la spécification de l'hypothèse n°3 et ses constantes ont été
  **gelées le 18 septembre 2026** (commit `26f8647`), onze jours avant
  le passage de l'hypothèse n°2 ;
- leurs empreintes — texte `bc6a8d17…`, constantes `47d593c5…` — sont
  vérifiées par `test_moteur` depuis ce jour et n'ont pas bougé ;
- aucune valeur de l'hypothèse n°3 ne peut donc avoir été choisie en
  connaissant le résultat du 29 septembre.

## 3. Ce que le passage de l'hypothèse n°2 a montré qui touche celle-ci

Écrit en entier, pour que rien ne soit découvert après coup :

- Le témoin de l'hypothèse n°2 réunissait **toutes les annonces sans
  bonne surprise** (CAR3 < +5 %), mauvaises surprises comprises, qui
  passaient ses E4 et E6 : **3 400 annonces**, achetées avec ses sorties,
  rendement moyen **+0,15 %** par trade. Les mauvaises surprises y sont
  mêlées aux annonces neutres, en nombre non affiché, **à l'achat**, avec
  un stop sous l'entrée et une sortie de régime de l'indice.
- Les comptes par condition portaient sur les bonnes surprises (E1 :
  1 038 sur 4 909) et sur des conditions de l'achat.
- **Rien** n'a été calculé avec les six conditions de l'hypothèse n°3, à
  la vente, avec ses sorties (stop au-dessus, thèse morte au-dessus de la
  SMA200) et ses coûts d'emprunt.

## 4. Ce qui ne peut être prouvé que par le propriétaire

Depuis le 18 septembre, le menu caché de `Carruos.bat` avait une option
**S** qui lançait `short.py` **directement sur 2024–2026**, sans rien
inscrire au registre. Si elle a été lancée une seule fois, l'hypothèse
n°3 a déjà regardé sa période de validation, et la période est brûlée
**pour elle** — cet amendement ne s'applique pas.

Le programme cherche la trace qu'elle laissait (`short-us.csv` à côté du
programme) et refuse le passage s'il la trouve. Mais une trace peut
manquer : la validation demande donc au propriétaire de déclarer, en
toutes lettres, qu'il ne l'a jamais lancée. La déclaration est gardée
avec la date de la validation.

## 5. La décision proposée

1. **La période de validation de l'hypothèse n°3 reste 2024-01-01 →
   2026-12-31**, un seul passage. Aucune constante ne change ;
   l'empreinte `47d593c5…` reste la même.
2. **Aucun seuil ne change**, z ≥ 2 compris. Le protocole ne relève pas
   la barre à chaque hypothèse : il limite leur nombre — **trois par an**.
   L'hypothèse n°3 est la troisième de 2026 : **c'est la dernière de
   l'année**. Relever un seuil maintenant serait un choix fait en
   connaissant le résultat de l'hypothèse n°2 — un degré de liberté de
   plus, pas une protection.
3. **Le partage est inscrit.** Le passage unique écrit au registre que
   la période a déjà été regardée par l'hypothèse n°2, avec l'empreinte
   de cet amendement et la date de sa validation. Un lecteur du registre
   voit deux hypothèses sur la même période, et le sait.
4. **Le programme l'exige.** Une période déjà regardée par une **autre**
   hypothèse ne part pas sans amendement validé : c'est vérifié par le
   code, pas par la mémoire.

## 6. Si cet amendement n'est pas validé

Si le propriétaire juge que 2024–2026 est touchée pour cette hypothèse
aussi, la seule autre voie honnête est une **période vierge**. Il
faudrait alors :

- une spécification **v1.1** dont la période de validation commence
  **après** sa date de rédaction — par exemple du 1ᵉʳ octobre 2026 au
  30 septembre 2028 ;
- une nouvelle empreinte des constantes, puisque la période en fait
  partie ;
- et attendre que ces données existent. Le compte de la préparation dira
  combien de temps il faut pour atteindre 200 trades.

Même voie si la déclaration du point 4 ne peut pas être faite.

---

*Un amendement écrit après le résultat serait une retouche. Celui-ci est
écrit avant, daté, haché, et ne vaut qu'une fois validé.*
