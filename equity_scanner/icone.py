"""Fabrique `carruos.ico` — le logo du raccourci et des fenetres.

    py -m equity_scanner.icone

Le dessin vient de `hud.icone()`, et de nulle part ailleurs : l'onglet
du navigateur, l'icone de chaque fenetre et le raccourci du Bureau sont
le meme SVG — l'hologramme de l'accueil, en medaillon. Ce module ne fait que le RASTERISER, taille par taille —
un cerf reduit de 256 a 16 pixels par Windows devient une tache ; dessine
directement a 16, il reste un cerf.

Il faut Chromium pour dessiner le SVG (Playwright) : c'est un outil de
fabrication, lance une fois quand le logo change, pas au demarrage du
programme. Le fichier produit est livre avec CARRUOS. L'assemblage du
fichier ICO, lui, est ecrit a la main et ne depend de rien : le format
est un en-tete, une entree par taille, puis les images.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from . import hud as hd

# 16 : barre des taches et onglet. 24 et 32 : barre de titre. 48 :
# Bureau en icones moyennes. 256 : grandes icones de l'explorateur.
TAILLES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
FICHIER = Path(__file__).resolve().parent.parent / "carruos.ico"

_PEINT = """async ([svg, n]) => {
  const img = new Image();
  img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));
  await img.decode();
  const c = document.createElement('canvas');
  c.width = c.height = n;
  const x = c.getContext('2d');
  x.clearRect(0, 0, n, n);
  x.imageSmoothingQuality = 'high';
  x.drawImage(img, 0, 0, n, n);
  return Array.from(x.getImageData(0, 0, n, n).data);
}"""


def bmp(n: int, rgba) -> bytes:
    """Une image ICO au format BMP 32 bits : en-tete DIB a hauteur
    DOUBLE (le format l'exige), pixels BGRA de bas en haut, puis le
    masque AND (tout opaque : la transparence est dans l'alpha)."""
    entete = struct.pack("<IiiHHIIiiII", 40, n, n * 2, 1, 32, 0,
                         n * n * 4, 0, 0, 0, 0)
    lignes = []
    for y in range(n - 1, -1, -1):
        o = y * n * 4
        lig = bytearray()
        for x in range(n):
            r, g, b, a = rgba[o + x * 4: o + x * 4 + 4]
            lig += bytes((b, g, r, a))
        lignes.append(bytes(lig))
    masque = b"\x00" * (((n + 31) // 32) * 4 * n)
    return entete + b"".join(lignes) + masque


def png(n: int, rgba) -> bytes:
    """PNG 32 bits. Windows le lit dans un ICO depuis Vista, et c'est
    dix fois plus leger qu'un BMP pour les grandes tailles."""
    brut = b"".join(b"\x00" + bytes(rgba[y * n * 4:(y + 1) * n * 4])
                    for y in range(n))

    def bloc(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + bloc(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(brut, 9))
            + bloc(b"IEND", b""))


def assemble(images: list[tuple[int, bytes]]) -> bytes:
    """Le fichier ICO : en-tete, une entree de 16 octets par taille, puis
    les images. Une largeur de 0 veut dire 256."""
    dec = 6 + 16 * len(images)
    ent, corps = b"", b""
    for n, data in images:
        d = 0 if n >= 256 else n
        ent += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(data), dec)
        corps += data
        dec += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + ent + corps


def lit(brut: bytes) -> list[dict]:
    """Relit un ICO : ce que `test_pages` verifie sur le fichier livre."""
    res, typ, n = struct.unpack("<HHH", brut[:6])
    if res != 0 or typ != 1:
        return []
    out = []
    for i in range(n):
        w, _h, _c, _r, _pl, bpp, taille, dec = struct.unpack(
            "<BBBBHHII", brut[6 + 16 * i: 22 + 16 * i])
        img = brut[dec:dec + taille]
        out.append({"taille": w or 256, "bpp": bpp, "octets": taille,
                    "complet": dec + taille <= len(brut),
                    "format": "PNG" if img[:4] == b"\x89PNG" else "BMP"})
    return out


def main() -> None:
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  Playwright est necessaire pour dessiner le logo :\n"
              "    py -m pip install playwright\n"
              "    py -m playwright install chromium\n"
              "  carruos.ico est deja livre avec CARRUOS : ce module ne sert\n"
              "  que si le logo change.")
        return
    import os

    async def dessine():
        async with async_playwright() as pw:
            chemin = os.environ.get("CARRUOS_CHROMIUM") or None
            br = await pw.chromium.launch(executable_path=chemin)
            pg = await br.new_page()
            await pg.goto("about:blank")
            images = []
            for n in TAILLES:
                # Dessine A CETTE TAILLE : les traits sont donnes en
                # pixels d'ecran, pas reduits d'un grand dessin.
                rgba = await pg.evaluate(_PEINT, [hd.icone(hd.TRACE, n), n])
                # BMP pour les petites tailles (compatibilite maximale),
                # PNG pour les grandes (poids).
                corps = png(n, rgba) if n >= 128 else bmp(n, rgba)
                images.append((n, corps))
                print(f"    {n:>3} px  {len(corps):>8} octets  "
                      f"{'PNG' if n >= 128 else 'BMP'}")
            await br.close()
            return images

    ico = assemble(asyncio.run(dessine()))
    FICHIER.write_bytes(ico)
    print(f"\n  {FICHIER.name} : {len(ico)} octets, {len(TAILLES)} tailles")


if __name__ == "__main__":
    main()
