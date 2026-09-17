"""Carruos - scanner actions."""

import sys
from pathlib import Path

# Mode cle USB : si un dossier "lib" existe a cote du paquet, les
# dependances (pandas, numpy, yfinance...) y sont embarquees et on les
# charge de la. Sur un poste ou elles sont deja installees, ce dossier
# n'existe pas et rien ne change.
_lib = Path(__file__).resolve().parent.parent / "lib"
if _lib.is_dir():
    chemin = str(_lib)
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
