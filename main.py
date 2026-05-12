"""
rename_pdf_ocr.py
─────────────────
Renomme les PDFs scannes en lisant le numero de serie situe
PHYSIQUEMENT EN DESSOUS du libelle "N° BON DE COMMANDE".
 
Methode :
  1. OCR avec donnees de position (pytesseract image_to_data).
  2. On localise le mot "COMMANDE" dans la page.
  3. On definit une zone de recherche = rectangle situe
       - horizontalement : autour du centre du libelle (+/- marge)
       - verticalement   : SOUS le libelle (de bas_libelle a bas_libelle + hauteur_ligne*3)
  4. On collecte tous les mots OCR qui tombent dans cette zone.
  5. On reconstitue le token (ex: C90005363/D221114_000139).
  6. Si le token contient Dxxxxxx_xxxxxx, on extrait ce sous-bloc.
     Sinon on utilise le token complet (/ remplace par _).
 
Dependances :
    pip install pymupdf pytesseract pillow
    + Tesseract OCR : https://github.com/UB-Mannheim/tesseract/wiki
 
Utilisation :
    python rename_pdf_ocr.py
"""
 
import os
import re
import sys
import fitz
import pytesseract
from PIL import Image
import io
import pandas as pd
 
# ──────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────
 
SCAN_DIR      = r"C:\Users\fto\Downloads\Scans\2022"
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_LANG      = "fra+eng"
RENDER_DPI    = 300
MAX_PAGES     = 2
DRY_RUN       = False
 
# ──────────────────────────────────────────────────────────────
# PATTERNS
# ──────────────────────────────────────────────────────────────
 
# Sous-pattern Dxxxxxx_xxxxxx (prioritaire si present dans le token)
D_PATTERN = re.compile(r'D\d{6}_\d{6}', re.IGNORECASE)
 
# Token numero de serie valide : lettre + alphanum + au moins un separateur /
# Ex : C90005363/D221114_000139  C506048577/123/BU00243
TOKEN_PATTERN = re.compile(r'^[A-Z][A-Z0-9]{2,}(?:[/\-][A-Z0-9]+)+$', re.IGNORECASE)
 
# Variantes OCR du mot "COMMANDE" (le dernier mot du libelle)
COMMANDE_RE = re.compile(r'C[O0]MMANDE', re.IGNORECASE)
 
# Caracteres interdits Windows
FORBIDDEN = re.compile(r'[\\/:*?"<>|\s]')
 
 
# ──────────────────────────────────────────────────────────────
# UTILITAIRES
# ──────────────────────────────────────────────────────────────
 
def configure_tesseract():
    if os.path.isfile(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    else:
        print(f"[WARN] Tesseract introuvable : {TESSERACT_CMD}")
        print("       https://github.com/UB-Mannheim/tesseract/wiki\n")
 
 
def sanitize(name: str) -> str:
    clean = FORBIDDEN.sub('_', name)
    clean = re.sub(r'_+', '_', clean)
    return clean.strip('_')
 
 
def page_to_image(page, dpi=RENDER_DPI, clip=None) -> Image.Image:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
    return Image.open(io.BytesIO(pix.tobytes("png")))
 
 
# ──────────────────────────────────────────────────────────────
# EXTRACTION PAR POSITION
# ──────────────────────────────────────────────────────────────
 
def extraire_numero_depuis_image(image: Image.Image) -> str | None:
    """
    Utilise pytesseract.image_to_data pour obtenir chaque mot avec
    ses coordonnees (left, top, width, height).
 
    Etapes :
      1. Trouver le mot "COMMANDE" (dernier mot du libelle).
      2. Definir une boite de recherche SOUS ce mot :
            x : de (centre_commande - largeur_page*0.30)
                a (centre_commande + largeur_page*0.30)
            y : de (bas_commande + 2px)
                a (bas_commande + hauteur_commande * 4)
      3. Collecter les mots OCR dans cette boite, les concatener.
      4. Appliquer la regle de nommage.
    """
    data = pytesseract.image_to_data(
        image,
        lang=OCR_LANG,
        config="--psm 3 --oem 3",
        output_type=pytesseract.Output.DICT
    )
 
    img_w, img_h = image.size
    n = len(data['text'])
 
    # ── 1. Localiser "COMMANDE" ──────────────────────────────────────────
    commande_boxes = []
    for i in range(n):
        word = str(data['text'][i]).strip()
        conf = int(data['conf'][i]) if str(data['conf'][i]).lstrip('-').isdigit() else -1
        if conf < 20:
            continue
        if COMMANDE_RE.fullmatch(word):
            left   = data['left'][i]
            top    = data['top'][i]
            width  = data['width'][i]
            height = data['height'][i]
            commande_boxes.append({
                'left': left, 'top': top,
                'width': width, 'height': height,
                'cx': left + width // 2,
                'bottom': top + height
            })
 
    if not commande_boxes:
        return None
 
    # On prend le "COMMANDE" le plus bas de la page (le tableau est en bas)
    label = max(commande_boxes, key=lambda b: b['bottom'])
 
    # ── 2. Definir la zone de recherche sous le libelle ──────────────────
    marge_h  = int(img_w * 0.28)          # +/- 28 % largeur autour du centre
    x_min    = max(0,     label['cx'] - marge_h)
    x_max    = min(img_w, label['cx'] + marge_h)
    y_min    = label['bottom'] + 2
    y_max    = label['bottom'] + label['height'] * 5   # ~2 lignes sous le libelle
 
    # ── 3. Collecter les mots dans la zone ───────────────────────────────
    mots_zone = []
    for i in range(n):
        word = str(data['text'][i]).strip()
        if not word:
            continue
        conf = int(data['conf'][i]) if str(data['conf'][i]).lstrip('-').isdigit() else -1
        if conf < 20:
            continue
        left   = data['left'][i]
        top    = data['top'][i]
        width  = data['width'][i]
        height = data['height'][i]
        cx     = left + width  // 2
        cy     = top  + height // 2
 
        if x_min <= cx <= x_max and y_min <= cy <= y_max:
            mots_zone.append((left, word))   # (position_x, mot)
 
    if not mots_zone:
        return None
 
    # Trier par position horizontale et concatener
    mots_zone.sort(key=lambda x: x[0])
    token = ''.join(m for _, m in mots_zone).upper()
 
    # Nettoyer les artefacts OCR courants : l espace entre chiffres/lettres
    token = re.sub(r'\s+', '', token)
 
    # ── 4. Valider et retourner le numero ─────────────────────────────────
    if not TOKEN_PATTERN.match(token):
        return None
 
    # Priorite : si le token contient Dxxxxxx_xxxxxx, on l'extrait
    d_match = D_PATTERN.search(token)
    if d_match:
        return d_match.group(0).upper()
 
    # Sinon : token complet avec / remplace par _
    return sanitize(token)
 
 
def extraire_numero_pdf(pdf_path: str) -> str | None:
    """
    Parcourt les premieres pages du PDF.
    Pour chaque page, essaie :
      1. Texte natif PyMuPDF  (PDF non scanne)
      2. OCR positionnel page entiere
      3. OCR positionnel zone basse (50-95 % hauteur) — scan de mauvaise qualite
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [ERREUR] {e}")
        return None
 
    for i in range(min(MAX_PAGES, len(doc))):
        page = doc[i]
 
        # 1) Texte natif : reconstruction ligne par ligne ─────────────────
        #    On cherche "COMMANDE" puis on lit la ligne suivante
        texte = page.get_text("text")
        numero = _extraire_depuis_texte_natif(texte)
        if numero:
            doc.close()
            return numero
 
        # 2) OCR positionnel page entiere ─────────────────────────────────
        try:
            img = page_to_image(page)
            numero = extraire_numero_depuis_image(img)
            if numero:
                doc.close()
                return numero
        except Exception as e:
            print(f"  [WARN] OCR page entiere p.{i+1} : {e}")
 
        # 3) OCR positionnel zone basse (50-95 %) ─────────────────────────
        try:
            r = page.rect
            zone = fitz.Rect(r.x0, r.y0 + r.height * 0.50,
                             r.x1, r.y0 + r.height * 0.95)
            img_bas = page_to_image(page, clip=zone)
            numero = extraire_numero_depuis_image(img_bas)
            if numero:
                doc.close()
                return numero
        except Exception as e:
            print(f"  [WARN] OCR zone basse p.{i+1} : {e}")
 
    doc.close()
    return None
 
 
def _extraire_depuis_texte_natif(texte: str) -> str | None:
    """
    Pour les PDFs non scannes : recherche la ligne contenant
    'BON DE COMMANDE' puis lit le token sur la ligne suivante.
    """
    lignes = texte.splitlines()
    for idx, ligne in enumerate(lignes):
        if re.search(r'B[O0]N\s+DE\s+C[O0]MMANDE', ligne, re.IGNORECASE):
            # Chercher le token sur les 3 lignes suivantes
            for j in range(1, 4):
                if idx + j >= len(lignes):
                    break
                candidate = lignes[idx + j].strip()
                if TOKEN_PATTERN.match(candidate):
                    d_match = D_PATTERN.search(candidate.upper())
                    if d_match:
                        return d_match.group(0).upper()
                    return sanitize(candidate.upper())
    return None
 
 
# ──────────────────────────────────────────────────────────────
# RENOMMAGE
# ──────────────────────────────────────────────────────────────
 
def renommer(src: str, dst: str) -> bool:
    base, ext = os.path.splitext(dst)
    target, n = dst, 1
    while os.path.exists(target):
        target = f"{base}_{n}{ext}"
        n += 1
    try:
        os.rename(src, target)
        if target != dst:
            print(f"  [INFO] Conflit -> renomme en {os.path.basename(target)}")
        return True
    except Exception as e:
        print(f"  [ERREUR] {e}")
        return False
 
 
# ──────────────────────────────────────────────────────────────
# TRAITEMENT DU DOSSIER
# ──────────────────────────────────────────────────────────────
 
def traiter_dossier(repertoire: str):
    if not os.path.isdir(repertoire):
        print(f"[ERREUR] Dossier introuvable : {repertoire}")
        sys.exit(1)
 
    pdfs = sorted(f for f in os.listdir(repertoire) if f.lower().endswith(".pdf"))
    if not pdfs:
        print(f"Aucun PDF trouve dans : {repertoire}")
        return
 
    print("=" * 65)
    print(f"  Dossier : {repertoire}")
    print(f"  PDFs    : {len(pdfs)}")
    print(f"  DPI     : {RENDER_DPI}")
    print(f"  Mode    : {'SIMULATION' if DRY_RUN else 'RENOMMAGE REEL'}")
    print("=" * 65 + "\n")
 
    ok = skip = echec = 0
 
    for nom in pdfs:
        src = os.path.join(repertoire, nom)
        print(f"[->] {nom}")
 
        numero = extraire_numero_pdf(src)
 
        if not numero:
            print("  [?] Numero introuvable — ignore.\n")
            echec += 1
            continue
 
        nouveau = f"{numero}.pdf"
        dst     = os.path.join(repertoire, nouveau)
 
        if nom == nouveau:
            print(f"  [OK] Deja correct ({nouveau}) — ignore.\n")
            skip += 1
            continue
 
        print(f"  [#] {numero}")
        print(f"      {nom}  -->  {nouveau}")
 
        if DRY_RUN:
            print("  [SIM]\n")
            ok += 1
        else:
            if renommer(src, dst):
                print("  [OK]\n")
                ok += 1
            else:
                echec += 1
 
    print("=" * 65)
    print(f"  Renommes      : {ok}")
    print(f"  Deja corrects : {skip}")
    print(f"  Echecs        : {echec}")
    print("=" * 65)
 
 
# ──────────────────────────────────────────────────────────────
# ENTREE
# ──────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    configure_tesseract()
    traiter_dossier(SCAN_DIR)
