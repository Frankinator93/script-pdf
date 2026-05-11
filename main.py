#!/usr/bin/env python3
"""
Script de renommage automatique de PDFs scannés.
Détecte le numéro de ticket dans le document et renomme en D12345_67890.
 
Dépendances :
    pip install pypdf pdfplumber pytesseract pillow pdf2image
    Tesseract OCR doit être installé :
        - Windows : https://github.com/UB-Mannheim/tesseract/wiki
        - Linux   : sudo apt install tesseract-ocr tesseract-ocr-fra
        - macOS   : brew install tesseract tesseract-lang
"""
 
import os
import re
import shutil
import sys
import logging
from pathlib import Path
 
# ── Librairies PDF ────────────────────────────────────────────────────────────
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
 
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
 
# ── Configuration ─────────────────────────────────────────────────────────────
 
# Dossier contenant les PDFs à traiter (modifiez selon votre besoin)
DOSSIER_SOURCE = r"C:\Scans"           # ou "/home/user/scans" sous Linux/macOS
 
# Dossier de destination pour les fichiers renommés
DOSSIER_DESTINATION = r"C:\Tickets_Renommes"
 
# Déplacer le fichier (True) ou le copier (False)
DEPLACER_FICHIER = True
 
# Langue OCR : "fra" (français), "eng" (anglais), "fra+eng" (les deux)
LANGUE_OCR = "fra+eng"
 
# Si Tesseract n'est pas dans le PATH (Windows surtout), indiquez le chemin :
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
 
# Patterns de numéros de ticket à détecter (ajoutez vos propres formats ici)
# Format cible final : D12345_67890
PATTERNS_TICKET = [
    # Format exact  D12345_67890  (avec ou sans espaces autour du _)
    r'\bD\s*(\d{3,6})\s*[_\-/]\s*(\d{3,6})\b',
 
    # Ticket n° 12345 / 67890  ou  Ticket: 12345-67890
    r'(?:ticket|n°|no\.?|num\.?|ref\.?|dossier)[^\d]*(\d{3,6})[^\d]+(\d{3,6})',
 
    # Référence 12345_67890  ou  Ref: 12345/67890
    r'(?:réf(?:érence)?|reference|ref)[^\d]*(\d{3,6})[^\d]+(\d{3,6})',
 
    # Deux blocs de chiffres séparés par _ - /  (fallback plus large)
    r'(\d{4,6})\s*[_\-/]\s*(\d{4,6})',
]
 
# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
 
 
# ── Fonctions ──────────────────────────────────────────────────────────────────
 
def extraire_texte_pdf(chemin_pdf: Path) -> str:
    """Tente d'extraire le texte d'un PDF, avec fallback OCR si le texte est vide."""
    texte = ""
 
    # 1) Extraction directe avec pdfplumber (PDFs textuels)
    if pdfplumber:
        try:
            with pdfplumber.open(chemin_pdf) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        texte += t + "\n"
        except Exception as e:
            log.warning(f"pdfplumber échoué sur {chemin_pdf.name} : {e}")
 
    # 2) Si pas de texte → OCR (PDFs scannés)
    if not texte.strip():
        if OCR_AVAILABLE:
            log.info(f"  → Texte vide, lancement OCR sur {chemin_pdf.name}…")
            try:
                images = convert_from_path(str(chemin_pdf), dpi=300)
                for img in images:
                    texte += pytesseract.image_to_string(img, lang=LANGUE_OCR) + "\n"
            except Exception as e:
                log.error(f"OCR échoué sur {chemin_pdf.name} : {e}")
        else:
            log.warning(
                "OCR non disponible (pytesseract / pdf2image non installés). "
                "Le PDF scanné ne pourra pas être lu."
            )
 
    return texte
 
 
def detecter_numero_ticket(texte: str) -> tuple[str, str] | None:
    """
    Cherche un numéro de ticket dans le texte.
    Retourne un tuple (partie1, partie2) ou None si aucun trouvé.
    """
    texte_norm = texte.replace("\n", " ").replace("\r", " ")
 
    for pattern in PATTERNS_TICKET:
        match = re.search(pattern, texte_norm, re.IGNORECASE)
        if match:
            p1, p2 = match.group(1), match.group(2)
            log.info(f"  → Ticket détecté : D{p1}_{p2}  (pattern : {pattern[:40]}…)")
            return p1, p2
 
    return None
 
 
def construire_nom_fichier(partie1: str, partie2: str, suffixe: int = 0) -> str:
    """Construit le nom de fichier au format D12345_67890.pdf"""
    base = f"D{partie1}_{partie2}"
    if suffixe:
        base = f"{base}_{suffixe}"
    return base + ".pdf"
 
 
def renommer_pdf(chemin_pdf: Path, dossier_dest: Path) -> bool:
    """
    Traite un fichier PDF : extraction → détection → renommage/déplacement.
    Retourne True si l'opération a réussi.
    """
    log.info(f"Traitement : {chemin_pdf.name}")
 
    texte = extraire_texte_pdf(chemin_pdf)
 
    if not texte.strip():
        log.warning(f"  ✗ Aucun texte extrait — fichier ignoré : {chemin_pdf.name}")
        return False
 
    resultat = detecter_numero_ticket(texte)
    if not resultat:
        log.warning(f"  ✗ Numéro de ticket introuvable dans : {chemin_pdf.name}")
        log.debug(f"    Extrait du texte :\n{texte[:500]}")
        return False
 
    p1, p2 = resultat
    nom_dest = construire_nom_fichier(p1, p2)
    chemin_dest = dossier_dest / nom_dest
 
    # Gestion des doublons
    compteur = 1
    while chemin_dest.exists():
        nom_dest = construire_nom_fichier(p1, p2, compteur)
        chemin_dest = dossier_dest / nom_dest
        compteur += 1
 
    try:
        if DEPLACER_FICHIER:
            shutil.move(str(chemin_pdf), str(chemin_dest))
            log.info(f"  ✔ Déplacé   → {chemin_dest}")
        else:
            shutil.copy2(str(chemin_pdf), str(chemin_dest))
            log.info(f"  ✔ Copié     → {chemin_dest}")
        return True
    except Exception as e:
        log.error(f"  ✗ Impossible de renommer/déplacer {chemin_pdf.name} : {e}")
        return False
 
 
def traiter_dossier(dossier_source: Path, dossier_dest: Path):
    """Parcourt le dossier source et traite tous les PDFs trouvés."""
    if not dossier_source.exists():
        log.error(f"Dossier source introuvable : {dossier_source}")
        sys.exit(1)
 
    dossier_dest.mkdir(parents=True, exist_ok=True)
 
    pdfs = sorted(dossier_source.glob("*.pdf")) + sorted(dossier_source.glob("*.PDF"))
    if not pdfs:
        log.warning(f"Aucun PDF trouvé dans : {dossier_source}")
        return
 
    log.info(f"{len(pdfs)} fichier(s) PDF trouvé(s) dans {dossier_source}\n")
 
    succes, echecs = 0, 0
    echecs_liste = []
 
    for pdf in pdfs:
        ok = renommer_pdf(pdf, dossier_dest)
        if ok:
            succes += 1
        else:
            echecs += 1
            echecs_liste.append(pdf.name)
        print()  # ligne vide entre chaque fichier
 
    # Récapitulatif
    log.info("=" * 60)
    log.info(f"RÉSUMÉ : {succes} renommé(s) avec succès, {echecs} échec(s).")
    if echecs_liste:
        log.warning("Fichiers non traités :")
        for f in echecs_liste:
            log.warning(f"  - {f}")
    log.info("=" * 60)
 
 
# ── Point d'entrée ─────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    # Possibilité de passer les dossiers en argument :
    # python renommer_pdf_ticket.py "C:\Scans" "C:\Destination"
    if len(sys.argv) >= 3:
        source = Path(sys.argv[1])
        dest   = Path(sys.argv[2])
    else:
        source = Path(DOSSIER_SOURCE)
        dest   = Path(DOSSIER_DESTINATION)
 
    traiter_dossier(source, dest)
