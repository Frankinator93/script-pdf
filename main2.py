"""
Script de renommage automatique de fichiers PDF
selon le numéro de demande au format Dxxxxx_xxxxx

Dossier cible : C:\\Users\\fto\\Downloads\\Scans\\2022
"""

import os
import re
import shutil
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Installation de pdfplumber en cours...")
    os.system("pip install pdfplumber")
    import pdfplumber

try:
    from pypdf import PdfReader
except ImportError:
    print("Installation de pypdf en cours...")
    os.system("pip install pypdf")
    from pypdf import PdfReader


# ─── Configuration ────────────────────────────────────────────────────────────

DOSSIER = r"C:\Users\fto\Downloads\Scans\2022"

# Regex : D suivi de 5 chiffres, underscore, 5 chiffres  →  ex: D12345_67890
PATTERN_DEMANDE = re.compile(r'D(\d{5})_(\d{5})', re.IGNORECASE)

# Si True  → simulation uniquement, aucun fichier n'est renommé
MODE_SIMULATION = False

# ──────────────────────────────────────────────────────────────────────────────


def extraire_texte_pdfplumber(chemin_pdf: Path) -> str:
    """Extraction du texte via pdfplumber (meilleure précision de layout)."""
    texte = []
    try:
        with pdfplumber.open(chemin_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texte.append(t)
    except Exception as e:
        print(f"    [pdfplumber] Erreur sur {chemin_pdf.name} : {e}")
    return "\n".join(texte)


def extraire_texte_pypdf(chemin_pdf: Path) -> str:
    """Extraction de secours via pypdf."""
    texte = []
    try:
        reader = PdfReader(str(chemin_pdf))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texte.append(t)
    except Exception as e:
        print(f"    [pypdf] Erreur sur {chemin_pdf.name} : {e}")
    return "\n".join(texte)


def trouver_numero_demande(texte: str) -> str | None:
    """Retourne le premier numéro de demande trouvé dans le texte, ou None."""
    match = PATTERN_DEMANDE.search(texte)
    if match:
        # Normaliser la casse → toujours majuscule
        return f"D{match.group(1)}_{match.group(2)}"
    return None


def renommer_pdfs(dossier: str, simulation: bool = False) -> None:
    dossier_path = Path(dossier)

    if not dossier_path.exists():
        print(f"❌  Le dossier n'existe pas : {dossier}")
        return

    pdfs = sorted(dossier_path.glob("*.pdf"))

    if not pdfs:
        print(f"⚠️   Aucun fichier PDF trouvé dans : {dossier}")
        return

    print(f"\n{'=' * 60}")
    print(f"  Dossier  : {dossier}")
    print(f"  PDFs     : {len(pdfs)} fichier(s)")
    print(f"  Mode     : {'SIMULATION' if simulation else 'RENOMMAGE RÉEL'}")
    print(f"{'=' * 60}\n")

    ok, deja_nomme, non_trouve, erreur = 0, 0, 0, 0

    for pdf_path in pdfs:
        print(f"📄  {pdf_path.name}")

        # 1. Le fichier est-il déjà nommé correctement ?
        if PATTERN_DEMANDE.match(pdf_path.stem):
            print(f"    ✅  Déjà au bon format — ignoré.\n")
            deja_nomme += 1
            continue

        # 2. Extraction du texte (pdfplumber en premier, pypdf en secours)
        texte = extraire_texte_pdfplumber(pdf_path)
        if not texte.strip():
            print("    ⚠️   pdfplumber : texte vide, tentative avec pypdf…")
            texte = extraire_texte_pypdf(pdf_path)

        if not texte.strip():
            print("    ❌  Impossible d'extraire le texte (PDF scanné ?).\n")
            erreur += 1
            continue

        # 3. Recherche du numéro de demande
        numero = trouver_numero_demande(texte)

        if not numero:
            print(f"    ❌  Numéro de demande introuvable (format D#####_#####).\n")
            non_trouve += 1
            continue

        # 4. Construction du nouveau nom
        nouveau_nom = f"{numero}.pdf"
        nouveau_chemin = pdf_path.parent / nouveau_nom

        # 5. Éviter les collisions de noms
        if nouveau_chemin.exists() and nouveau_chemin != pdf_path:
            compteur = 1
            while nouveau_chemin.exists():
                nouveau_nom = f"{numero}_{compteur}.pdf"
                nouveau_chemin = pdf_path.parent / nouveau_nom
                compteur += 1
            print(f"    ⚠️   Collision détectée → nouveau nom : {nouveau_nom}")

        print(f"    🔄  {pdf_path.name}  →  {nouveau_nom}")

        if not simulation:
            try:
                pdf_path.rename(nouveau_chemin)
                print(f"    ✅  Renommé avec succès.\n")
                ok += 1
            except Exception as e:
                print(f"    ❌  Échec du renommage : {e}\n")
                erreur += 1
        else:
            print(f"    [SIMULATION — aucune modification]\n")
            ok += 1

    # Récapitulatif
    print(f"{'=' * 60}")
    print(f"  ✅  Renommés     : {ok}")
    print(f"  ⏭️   Déjà OK      : {deja_nomme}")
    print(f"  ⚠️   N° introuvable: {non_trouve}")
    print(f"  ❌  Erreurs       : {erreur}")
    print(f"{'=' * 60}\n")

    if simulation:
        print("ℹ️   Mode simulation activé : aucun fichier n'a été modifié.")
        print("    Passez MODE_SIMULATION = False pour appliquer les renommages.\n")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    renommer_pdfs(DOSSIER, simulation=MODE_SIMULATION)
