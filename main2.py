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
# PATTERNS
# ──────────────────────────────────────────────
 
# PRIORITE 1 — format Dxxxxxx_xxxxxx  (ex: D221114_000139)
DEMANDE_PATTERN = re.compile(
    r'(?<![A-Z0-9])(D\d{6}_\d{6})(?!\d)',
    re.IGNORECASE
)
 
# PRIORITE 2 (fallback) — numero complet qui suit le libelle "N° BON DE COMMANDE"
# Gere les variantes OCR du libelle : "N° BON", "No BON", "N BON", "N0 BON", etc.
# Capture ensuite le numero sur la meme ligne ou la suivante.
# Ex: "C506048577/123/BU00243"  ou  "C90005363/D221114_000139"
LABEL_PATTERN = re.compile(
    r'N\s*[o\u00b0O0]?\s*(?:BON\s+DE\s+COMMANDE|B[O0]N\s+DE\s+C[O0]MMANDE)'
    r'[^\n]{0,40}\n?\s*([A-Z0-9][A-Z0-9/\-_.]{3,60})',
    re.IGNORECASE
)
 
# Caracteres interdits dans un nom de fichier Windows
FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\s]')
 
 
# ──────────────────────────────────────────────
# FONCTIONS UTILITAIRES
# ──────────────────────────────────────────────
 
def configure_tesseract():
    """Configure le chemin de Tesseract si le fichier existe."""
    if os.path.isfile(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    else:
        print(f"[AVERTISSEMENT] Tesseract introuvable a : {TESSERACT_CMD}")
        print("  --> Assurez-vous que Tesseract est installe et que TESSERACT_CMD est correct.")
        print("  --> Telechargement : https://github.com/UB-Mannheim/tesseract/wiki\n")
 
 
def sanitize_filename(name: str) -> str:
    """
    Remplace les caracteres interdits dans un nom de fichier Windows par '_'.
    Compresse les '_' consecutifs et supprime ceux en debut/fin.
    """
    clean = FORBIDDEN_CHARS.sub('_', name)
    clean = re.sub(r'_+', '_', clean)
    return clean.strip('_')
 
 
def pdf_page_to_image(page, dpi: int = RENDER_DPI, clip_rect=None) -> Image.Image:
    """
    Convertit une page PDF (ou une zone clip_rect) en image PIL via PyMuPDF.
    clip_rect : fitz.Rect exprime en points PDF (avant zoom).
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
    psm=3 : page complete (detection automatique)
    psm=6 : bloc de texte uniforme (zone isolee)
    """
    config = f"--psm {psm} --oem 3"
    return pytesseract.image_to_string(image, lang=OCR_LANG, config=config)
 
 
# ──────────────────────────────────────────────
# LOGIQUE DE RECHERCHE AVEC PRIORITE
# ──────────────────────────────────────────────
 
def find_priority_number(text: str):
    """
    Cherche en PRIORITE le format Dxxxxxx_xxxxxx dans le texte.
    Retourne (numero, 'priority') ou None.
    """
    match = DEMANDE_PATTERN.search(text)
    if match:
        return (match.group(1).upper(), 'priority')
    return None
 
 
def find_fallback_number(text: str):
    """
    Cherche le numero complet sous "N° BON DE COMMANDE" (mode FALLBACK).
    Retourne (numero_sanitize, 'fallback') ou None.
    """
    match = LABEL_PATTERN.search(text)
    if match:
        raw = match.group(1).strip()
        if len(raw) < 4:
            return None
        return (sanitize_filename(raw.upper()), 'fallback')
    return None
 
 
def search_in_text(text: str):
    """
    Applique la recherche prioritaire puis fallback sur un texte.
    Retourne (numero, mode) ou None.
    """
    result = find_priority_number(text)
    if result:
        return result
    return find_fallback_number(text)
 
 
def extract_demande_number(pdf_path: str):
    """
    Ouvre le PDF, parcourt les premieres pages et retourne :
      (numero, mode)  avec mode = 'priority' | 'fallback'
    ou None si aucun numero n'est trouve.
 
    A chaque passe OCR, un resultat 'priority' est retourne immediatement.
    Un resultat 'fallback' est conserve et retourne seulement si aucun
    'priority' n'est trouve sur l'ensemble des pages analysees.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [ERREUR] Impossible d'ouvrir {pdf_path} : {e}")
        return None
 
    pages_to_check = min(MAX_PAGES, len(doc))
    best_fallback = None   # meilleur fallback toutes passes confondues
 
    for page_num in range(pages_to_check):
        page = doc[page_num]
 
        # ── Passe 1 : texte natif ─────────────────────────────────────────
        native_text = page.get_text()
        result = search_in_text(native_text)
        if result:
            if result[1] == 'priority':
                doc.close()
                return result
            if best_fallback is None:
                best_fallback = result
 
        # ── Passe 2 : OCR page entiere ────────────────────────────────────
        try:
            img_full = pdf_page_to_image(page)
            result = search_in_text(ocr_image(img_full, psm=3))
            if result:
                if result[1] == 'priority':
                    doc.close()
                    return result
                if best_fallback is None:
                    best_fallback = result
        except Exception as e:
            print(f"  [AVERTISSEMENT] OCR page entiere echoue (page {page_num+1}) : {e}")
 
        # ── Passe 3 : OCR zone ciblee (bande 50-90 % hauteur) ────────────
        try:
            rect = page.rect
            strip = fitz.Rect(
                rect.x0,
                rect.y0 + rect.height * 0.50,   # debut a 50 % de la hauteur
                rect.x1,
                rect.y0 + rect.height * 0.90,   # fin   a 90 % de la hauteur
            )
            img_strip = pdf_page_to_image(page, clip_rect=strip)
            result = search_in_text(ocr_image(img_strip, psm=6))
            if result:
                if result[1] == 'priority':
                    doc.close()
                    return result
                if best_fallback is None:
                    best_fallback = result
        except Exception as e:
            print(f"  [AVERTISSEMENT] OCR zone ciblee echoue (page {page_num+1}) : {e}")
 
    doc.close()
    return best_fallback   # None si rien trouve du tout
 
 
# ──────────────────────────────────────────────
# RENOMMAGE
# ──────────────────────────────────────────────
 
def safe_rename(src: str, dst: str) -> bool:
    """
    Renomme src -> dst.
    Si dst existe deja, ajoute un suffixe _1, _2 ... pour eviter l'ecrasement.
    Retourne True si succes.
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
    """Parcourt le dossier et renomme les PDFs trouves."""
    if not os.path.isdir(directory):
        print(f"[ERREUR] Le dossier n'existe pas : {directory}")
        sys.exit(1)
 
    pdf_files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
 
    if not pdf_files:
        print(f"Aucun fichier PDF trouve dans : {directory}")
        return
 
    print("=" * 65)
    print(f"  Dossier  : {directory}")
    print(f"  PDFs     : {len(pdf_files)} fichier(s)")
    print(f"  DPI OCR  : {RENDER_DPI}")
    print(f"  Mode     : {'SIMULATION (DRY RUN)' if DRY_RUN else 'RENOMMAGE REEL'}")
    print("=" * 65 + "\n")
 
    renamed   = 0
    skipped   = 0
    not_found = 0
    fallbacks = 0
 
    for filename in sorted(pdf_files):
        src_path = os.path.join(directory, filename)
        print(f"[->] {filename}")
 
        extraction = extract_demande_number(src_path)
 
        if extraction is None:
            print("  [?] Aucun numero trouve (Dxxxxxx_xxxxxx ni numero complet) -- ignore.\n")
            not_found += 1
            continue
 
        numero, mode = extraction
        new_filename  = f"{numero}.pdf"
        dst_path      = os.path.join(directory, new_filename)
        mode_label    = "[PRIORITE D]    " if mode == 'priority' else "[FALLBACK complet]"
 
        # Deja bien nomme ?
        if filename == new_filename:
            print(f"  [OK] Deja nomme correctement ({new_filename}) -- ignore.\n")
            skipped += 1
            continue
 
        print(f"  {mode_label} Numero : {numero}")
        print(f"  [->] {filename}  -->  {new_filename}")
 
        if mode == 'fallback':
            fallbacks += 1
 
        if DRY_RUN:
            print("  [SIM] (simulation, aucune modification effectuee)\n")
            renamed += 1
        else:
            if safe_rename(src_path, dst_path):
                print("  [OK] Renomme avec succes.\n")
                renamed += 1
            else:
                not_found += 1
 
    # ── Recapitulatif ──
    print("=" * 65)
    print(f"  Renommes          : {renamed}  (dont {fallbacks} via fallback numero complet)")
    print(f"  Deja corrects     : {skipped}")
    print(f"  Non traites       : {not_found}")
    print("=" * 65)
 
 
# ──────────────────────────────────────────────
# POINT D'ENTREE
# ──────────────────────────────────────────────
 
if __name__ == "__main__":
    configure_tesseract()
    process_directory(SCAN_DIR)
