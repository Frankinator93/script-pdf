"""
rename_pdf_ocr.py
-----------------
Renomme les fichiers PDF scannés selon leur numéro de demande
au format Dxxxxxx_xxxxxx (x = chiffre) en utilisant l'OCR.
 
Dépendances :
    pip install pymupdf pytesseract pillow
    + Tesseract OCR installé sur le système :
        Windows : https://github.com/UB-Mannheim/tesseract/wiki
        (ajouter le chemin dans PATH ou configurer TESSERACT_CMD ci-dessous)
 
Utilisation :
    python rename_pdf_ocr.py
"""
 
import os
import re
import sys
import shutil
import fitz          # PyMuPDF
import pytesseract
from PIL import Image
import io
 
# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
 
# Dossier contenant les PDFs à renommer
SCAN_DIR = r"C:\Users\fto\Downloads\Scans\2022"
 
# Chemin vers l'exécutable Tesseract (adapter si nécessaire)
# Exemple Windows : r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD = r"C:\Users\fto\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
 
# Langue OCR (fra = français, eng = anglais, fra+eng = les deux)
OCR_LANG = "fra+eng"
 
# Résolution de rendu des pages (DPI) – augmenter si l'OCR rate des numéros
RENDER_DPI = 300
 
# Nombre de pages à analyser par PDF (les premières pages suffisent en général)
MAX_PAGES = 3
 
# Mode simulation : True = affiche les renommages SANS les effectuer
DRY_RUN = False
 
# ──────────────────────────────────────────────
# PATTERN du numéro de demande
# ──────────────────────────────────────────────
# Le champ "N° BON DE COMMANDE" contient par exemple : C90005363/D221114_000139
# On extrait uniquement la partie  D + 6 chiffres + _ + 6 chiffres
# Le séparateur avant le D peut être / \ | espace ou début de chaîne.
DEMANDE_PATTERN = re.compile(r'(?<![A-Z0-9])(D\d{6}_\d{6})(?!\d)', re.IGNORECASE)
 
 
# ──────────────────────────────────────────────
# FONCTIONS
# ──────────────────────────────────────────────
 
def configure_tesseract():
    """Configure le chemin de Tesseract si le fichier existe."""
    if os.path.isfile(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    else:
        print(f"[AVERTISSEMENT] Tesseract introuvable à : {TESSERACT_CMD}")
        print("  → Assurez-vous que Tesseract est installé et que TESSERACT_CMD est correct.")
        print("  → Téléchargement : https://github.com/UB-Mannheim/tesseract/wiki\n")
 
 
def pdf_page_to_image(page, dpi: int = RENDER_DPI, clip_rect=None) -> Image.Image:
    """
    Convertit une page PDF (ou une zone clip_rect) en image PIL via PyMuPDF.
    clip_rect : fitz.Rect exprimé en points PDF (avant zoom).
    """
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    if clip_rect:
        pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip_rect)
    else:
        pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png")))
 
 
def ocr_image(image: Image.Image, psm: int = 3) -> str:
    """
    Applique l'OCR Tesseract sur une image PIL et retourne le texte.
    psm=3  → page complète (défaut)
    psm=6  → bloc de texte uniforme (bon pour une zone isolée)
    """
    config = f"--psm {psm} --oem 3"
    return pytesseract.image_to_string(image, lang=OCR_LANG, config=config)
 
 
def search_in_text(text: str) -> str | None:
    """Cherche le pattern dans un texte et retourne la valeur normalisée."""
    match = DEMANDE_PATTERN.search(text)
    return match.group(1).upper() if match else None
 
 
def extract_demande_number(pdf_path: str) -> str | None:
    """
    Ouvre le PDF, parcourt les premières pages et retourne le premier
    numéro de demande trouvé (format Dxxxxxx_xxxxxx).
 
    Stratégie par page :
      1. Texte natif (si le PDF n'est pas un scan pur).
      2. OCR page entière à RENDER_DPI.
      3. OCR ciblé sur la moitié inférieure de la page
         (zone où se trouve le tableau "N° BON DE COMMANDE").
 
    Retourne None si aucun numéro n'est trouvé sur toutes les pages.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [ERREUR] Impossible d'ouvrir {pdf_path} : {e}")
        return None
 
    pages_to_check = min(MAX_PAGES, len(doc))
 
    for page_num in range(pages_to_check):
        page = doc[page_num]
 
        # ── 1) Texte natif ────────────────────────────────────────────────
        native_text = page.get_text()
        result = search_in_text(native_text)
        if result:
            doc.close()
            return result
 
        # ── 2) OCR page entière ───────────────────────────────────────────
        try:
            img_full = pdf_page_to_image(page)
            result = search_in_text(ocr_image(img_full, psm=3))
            if result:
                doc.close()
                return result
        except Exception as e:
            print(f"  [AVERTISSEMENT] OCR page entière échoué (page {page_num+1}) : {e}")
 
        # ── 3) OCR ciblé — moitié basse de la page ────────────────────────
        # Le champ "N° BON DE COMMANDE" est typiquement dans la bande
        # comprise entre 55 % et 85 % de la hauteur de la page.
        try:
            rect = page.rect                                # dimensions en pt
            strip = fitz.Rect(
                rect.x0,
                rect.y0 + rect.height * 0.50,   # début à 50 % de la hauteur
                rect.x1,
                rect.y0 + rect.height * 0.90,   # fin    à 90 % de la hauteur
            )
            img_strip = pdf_page_to_image(page, clip_rect=strip)
            result = search_in_text(ocr_image(img_strip, psm=6))
            if result:
                doc.close()
                return result
        except Exception as e:
            print(f"  [AVERTISSEMENT] OCR zone ciblée échoué (page {page_num+1}) : {e}")
 
    doc.close()
    return None
 
 
def safe_rename(src: str, dst: str) -> bool:
    """
    Renomme src → dst.
    Si dst existe déjà, ajoute un suffixe _1, _2 … pour éviter l'écrasement.
    Retourne True si succès.
    """
    base, ext = os.path.splitext(dst)
    counter = 1
    target = dst
    while os.path.exists(target):
        target = f"{base}_{counter}{ext}"
        counter += 1
 
    try:
        os.rename(src, target)
        return True
    except Exception as e:
        print(f"  [ERREUR] Renommage impossible : {e}")
        return False
 
 
def process_directory(directory: str):
    """Parcourt le dossier et renomme les PDFs trouvés."""
    if not os.path.isdir(directory):
        print(f"[ERREUR] Le dossier n'existe pas : {directory}")
        sys.exit(1)
 
    pdf_files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
 
    if not pdf_files:
        print(f"Aucun fichier PDF trouvé dans : {directory}")
        return
 
    print(f"{'=' * 60}")
    print(f"  Dossier  : {directory}")
    print(f"  PDFs     : {len(pdf_files)} fichier(s)")
    print(f"  DPI OCR  : {RENDER_DPI}")
    print(f"  Mode     : {'SIMULATION (DRY RUN)' if DRY_RUN else 'RENOMMAGE RÉEL'}")
    print(f"{'=' * 60}\n")
 
    renamed  = 0
    skipped  = 0
    not_found = 0
 
    for filename in sorted(pdf_files):
        src_path = os.path.join(directory, filename)
        print(f"[→] {filename}")
 
        demande_num = extract_demande_number(src_path)
 
        if demande_num is None:
            print(f"  [?] Numéro de demande non trouvé — fichier ignoré.\n")
            not_found += 1
            continue
 
        new_filename = f"{demande_num}.pdf"
        dst_path = os.path.join(directory, new_filename)
 
        # Déjà bien nommé ?
        if filename == new_filename:
            print(f"  [✓] Déjà nommé correctement ({new_filename}) — ignoré.\n")
            skipped += 1
            continue
 
        print(f"  [✓] Numéro trouvé : {demande_num}")
        print(f"  [→] Renommage : {filename}  →  {new_filename}")
 
        if DRY_RUN:
            print(f"  [SIM] (simulation, aucune modification effectuée)\n")
            renamed += 1
        else:
            if safe_rename(src_path, dst_path):
                print(f"  [OK] Renommé avec succès.\n")
                renamed += 1
            else:
                not_found += 1
 
    # ── Récapitulatif ──
    print(f"{'=' * 60}")
    print(f"  Renommés       : {renamed}")
    print(f"  Déjà corrects  : {skipped}")
    print(f"  Non traités    : {not_found}")
    print(f"{'=' * 60}")
 
 
# ──────────────────────────────────────────────
# POINT D'ENTRÉE
# ──────────────────────────────────────────────
 
if __name__ == "__main__":
    configure_tesseract()
    process_directory(SCAN_DIR)
