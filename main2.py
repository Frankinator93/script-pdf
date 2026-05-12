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
# Correspond à : D123456_789012  (D + 6 chiffres + _ + 6 chiffres)
DEMANDE_PATTERN = re.compile(r'D\d{6}_\d{6}', re.IGNORECASE)
 
 
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
 
 
def pdf_page_to_image(page, dpi: int = RENDER_DPI) -> Image.Image:
    """Convertit une page PDF en image PIL via PyMuPDF."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)   # 72 pt/pouce natif
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))
 
 
def ocr_image(image: Image.Image) -> str:
    """Applique l'OCR Tesseract sur une image et retourne le texte."""
    # PSM 3 = page complète, détection automatique
    config = "--psm 3"
    return pytesseract.image_to_string(image, lang=OCR_LANG, config=config)
 
 
def extract_demande_number(pdf_path: str) -> str | None:
    """
    Ouvre le PDF, parcourt les premières pages avec OCR et retourne
    le premier numéro de demande trouvé (format Dxxxxxx_xxxxxx).
    Retourne None si aucun numéro n'est trouvé.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [ERREUR] Impossible d'ouvrir {pdf_path} : {e}")
        return None
 
    pages_to_check = min(MAX_PAGES, len(doc))
 
    for page_num in range(pages_to_check):
        page = doc[page_num]
 
        # 1) Essai extraction texte natif (rapide)
        native_text = page.get_text()
        match = DEMANDE_PATTERN.search(native_text)
        if match:
            doc.close()
            return match.group(0).upper()
 
        # 2) Fallback OCR sur l'image de la page (PDF scanné)
        try:
            image = pdf_page_to_image(page)
            ocr_text = ocr_image(image)
            match = DEMANDE_PATTERN.search(ocr_text)
            if match:
                doc.close()
                return match.group(0).upper()
        except Exception as e:
            print(f"  [AVERTISSEMENT] OCR échoué page {page_num + 1} de {pdf_path} : {e}")
 
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
