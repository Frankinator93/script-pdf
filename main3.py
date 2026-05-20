"""
Renommage automatique des bons de livraison PDF (scannés)
=========================================================
Lit chaque PDF via OCR (Tesseract), extrait le numéro situé
SOUS "N° BON DE COMMANDE" et renomme le fichier en conséquence.

Dépendances à installer :
    pip install pymupdf pytesseract pillow
    + Tesseract-OCR : https://github.com/UB-Mannheim/tesseract/wiki
      (cocher "French" lors de l'installation ou installer le pack fra)
"""

import os
import re
import sys
import shutil
import logging
from pathlib import Path

import fitz          # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io

# ── Configuration ────────────────────────────────────────────────────────────

DOSSIER = r"C:\Users\fto\Downloads\Scans\2022"

# Chemin vers tesseract.exe (modifier si nécessaire)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Résolution de rendu (DPI) — augmenter si les documents sont peu lisibles
DPI = 300

# Langue OCR : fra = français, eng = anglais (ajouter les deux pour plus de robustesse)
LANGUE_OCR = "fra+eng"

# Si True, simule uniquement (affiche les renommages sans les faire)
DRY_RUN = False

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(DOSSIER, "_renommage_log.txt"),
            encoding="utf-8",
            mode="a",
        ),
    ],
)
log = logging.getLogger(__name__)

# ── Prétraitement image pour améliorer l'OCR ─────────────────────────────────

def pretraiter_image(pil_img: Image.Image) -> Image.Image:
    """
    Améliore la lisibilité avant l'OCR :
      - Niveaux de gris
      - Augmentation du contraste
      - Légère netteté
      - Binarisation (noir/blanc)
    """
    img = pil_img.convert("L")                          # niveaux de gris
    img = ImageEnhance.Contrast(img).enhance(2.0)       # contraste ×2
    img = img.filter(ImageFilter.SHARPEN)               # netteté
    # Binarisation adaptative simple (seuil 160)
    img = img.point(lambda x: 255 if x > 160 else 0, "1")
    return img.convert("RGB")


# ── Extraction OCR d'une page PDF ────────────────────────────────────────────

def ocr_page(doc: fitz.Document, page_num: int) -> str:
    """
    Rasterise la page et applique Tesseract.
    Retourne le texte extrait (chaîne vide si échec).
    """
    page = doc[page_num]
    mat = fitz.Matrix(DPI / 72, DPI / 72)   # facteur de mise à l'échelle
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    img = pretraiter_image(img)

    try:
        texte = pytesseract.image_to_string(
            img,
            lang=LANGUE_OCR,
            config="--oem 3 --psm 6",   # oem3 = LSTM, psm6 = bloc de texte uniforme
        )
        return texte
    except Exception as exc:
        log.warning(f"  Erreur OCR page {page_num} : {exc}")
        return ""


# ── Extraction du numéro de bon de commande ──────────────────────────────────

# Patterns reconnus :
#   C900063448/D230606_000548
#   C506048577/123/BU00243
#   C900063448D230606000548   (sans séparateurs, OCR dégradé)
#   REF-2022-001234           (autres formats)
PATTERNS_BC = [
    # Format standard avec séparateurs slash ou underscore
    r"[A-Z]{1,3}[\d]{6,}(?:[/_\-][\w\d]+)+",
    # Format alphanumérique générique (≥ 8 chars, commence par lettre)
    r"[A-Z]{1,3}\d{8,}",
    # Format numérique pur (≥ 8 chiffres)
    r"\b\d{10,}\b",
]

# Mots-clés qui précèdent le numéro (avec tolérance OCR)
LABELS_BC = [
    r"N[°o\*\.]?\s*BON\s+DE\s+COMMANDE",
    r"N[°o\*\.]?\s*(?:BON|BDC|BC)\s*(?:DE)?\s*COMMANDE",
    r"BON\s+DE\s+COMMANDE",
    r"N[°o\*\.]\s*COMMANDE",
    r"REF(?:ERENCE)?\s+COMMANDE",
    r"ORDER\s+(?:N[°o\*\.]|NUMBER|REF)",
]

def extraire_numero_bc(texte: str) -> str | None:
    """
    Cherche le numéro de bon de commande dans le texte OCR.

    Stratégie :
      1. Repère la ligne contenant un label "N° BON DE COMMANDE"
      2. Prend le token valide sur la même ligne OU la ligne suivante
      3. Sinon tente les patterns génériques sur l'ensemble du texte
    """
    lignes = texte.splitlines()

    for i, ligne in enumerate(lignes):
        for label in LABELS_BC:
            if re.search(label, ligne, re.IGNORECASE):
                # Cherche d'abord sur la même ligne (après le label)
                suite = re.split(label, ligne, flags=re.IGNORECASE, maxsplit=1)
                candidats = [suite[-1].strip()] if len(suite) > 1 else []

                # Puis sur la ligne immédiatement suivante
                if i + 1 < len(lignes):
                    candidats.append(lignes[i + 1].strip())

                # Et deux lignes plus bas (formulaires avec mise en page variée)
                if i + 2 < len(lignes):
                    candidats.append(lignes[i + 2].strip())

                for cand in candidats:
                    # Nettoie les espaces parasites introduits par l'OCR
                    cand_clean = re.sub(r"\s+", "", cand)
                    for pat in PATTERNS_BC:
                        m = re.search(pat, cand_clean, re.IGNORECASE)
                        if m and len(m.group()) >= 6:
                            return nettoyer_nom(m.group())
                break  # label trouvé, passe à la ligne suivante

    # Dernier recours : patterns génériques sur tout le texte
    for pat in PATTERNS_BC:
        for m in re.finditer(pat, texte, re.IGNORECASE):
            val = nettoyer_nom(m.group())
            if len(val) >= 6:
                return val

    return None


def nettoyer_nom(valeur: str) -> str:
    """Supprime les caractères interdits dans un nom de fichier Windows."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", valeur).strip("_. ")


# ── Traitement d'un fichier PDF ───────────────────────────────────────────────

def traiter_pdf(chemin: Path) -> bool:
    """
    Ouvre le PDF, parcourt ses pages (max 3) pour trouver le numéro BC.
    Renomme le fichier si trouvé.
    Retourne True si succès.
    """
    log.info(f"Traitement : {chemin.name}")
    try:
        doc = fitz.open(str(chemin))
    except Exception as exc:
        log.error(f"  Impossible d'ouvrir le PDF : {exc}")
        return False

    numero = None
    # Parcourt au maximum les 3 premières pages (le bon est généralement en page 1)
    for page_num in range(min(3, len(doc))):
        texte = ocr_page(doc, page_num)
        if texte:
            log.debug(f"  [Page {page_num+1}] Texte OCR extrait ({len(texte)} chars)")
        numero = extraire_numero_bc(texte)
        if numero:
            log.info(f"  → Numéro BC trouvé (page {page_num+1}) : {numero}")
            break

    doc.close()

    if not numero:
        log.warning(f"  ✗ Numéro BC introuvable dans {chemin.name}")
        return False

    # Construction du nouveau nom
    nouveau_nom = f"{numero}.pdf"
    nouveau_chemin = chemin.parent / nouveau_nom

    # Évite l'écrasement si un fichier du même nom existe déjà
    if nouveau_chemin.exists() and nouveau_chemin != chemin:
        compteur = 1
        while nouveau_chemin.exists():
            nouveau_nom = f"{numero}_{compteur}.pdf"
            nouveau_chemin = chemin.parent / nouveau_nom
            compteur += 1
        log.warning(f"  Conflit de nom → renommé en {nouveau_nom}")

    if chemin == nouveau_chemin:
        log.info(f"  ✓ Déjà nommé correctement : {chemin.name}")
        return True

    if DRY_RUN:
        log.info(f"  [DRY-RUN] {chemin.name}  →  {nouveau_nom}")
    else:
        chemin.rename(nouveau_chemin)
        log.info(f"  ✓ Renommé : {chemin.name}  →  {nouveau_nom}")

    return True


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    dossier = Path(DOSSIER)
    if not dossier.exists():
        log.error(f"Dossier introuvable : {dossier}")
        sys.exit(1)

    pdfs = sorted(dossier.glob("*.pdf"))
    if not pdfs:
        log.info("Aucun fichier PDF trouvé dans le dossier.")
        return

    log.info(f"{'='*60}")
    log.info(f"Dossier  : {dossier}")
    log.info(f"PDFs     : {len(pdfs)}")
    log.info(f"DPI OCR  : {DPI}   Langue : {LANGUE_OCR}")
    log.info(f"Mode     : {'DRY-RUN (simulation)' if DRY_RUN else 'RÉEL'}")
    log.info(f"{'='*60}")

    succes, echecs = 0, 0
    for pdf in pdfs:
        if traiter_pdf(pdf):
            succes += 1
        else:
            echecs += 1

    log.info(f"{'='*60}")
    log.info(f"Résultat : {succes} renommés  |  {echecs} non traités")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    main()
