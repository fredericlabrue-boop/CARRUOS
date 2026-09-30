# Archives des moteurs

Chaque fichier est une copie **à l'octet près** d'un moteur tel qu'il a
tourné pour un passage inscrit au registre. Son nom porte le début de son
empreinte SHA256, celle que le registre cite sous « Code du moteur ».

On ne les modifie jamais : `test_moteur` recalcule leur empreinte et la
compare à celle du registre. Ils ne sont pas importés par le programme.

| fichier | hypothèse | passage | empreinte complète |
|---|---|---|---|
| `pead-4f038443979fcf6f.py` | n°2, dérive post-annonce | passage unique 2024-2026 du 29/09/2026, NO-GO | `4f038443979fcf6fef8dfe70b24d626668d70aa5c50515488d2eb1f989afc361` |

Pour rejouer exactement ce qui a tourné : remettre ce fichier à la place
de `equity_scanner/pead.py` dans une copie du programme.
