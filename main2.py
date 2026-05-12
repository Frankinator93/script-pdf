#!/usr/bin/env python3
"""
rename_pdf_by_demande.py
------------------------
Renomme les fichiers PDF d'un dossier selon leur numéro de demande
au format Dxxxxx_xxxxx (ex: D12345_67890) extrait du contenu du PDF.

Usage:
    python rename_pdf_by_demande.py <dossier>
    python rename_pdf_by_demande.py <dossier> --dry-run   # simulation sans renommer
    python rename_pdf_by_demande.py <dossier> --recursive  # inclure les sous-dossiers
"""

import argparse
import re
import sys
from pathlib import Path

# --- Dépendances ---
# pip install pdfplumber pypdf
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

if not HAS_PDFPLUMBER and not HAS_PYPDF:
    print("Erreur : installez au moins une bibliothèque PDF :")
    print("  pip install pdfplumber pypdf")
    sys.exit(1)


# Regex : D suivi de 5 chiffres, underscore, 5 chiffres
PATTERN = re.compile(r'\bD\d{5}_\d{5}\b')


def extract_text_pdfplumber(pdf_path: Path) -> str:
    """Extraction de texte via pdfplumber (meilleur pour les PDFs complexes)."""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
                # Arrêt dès que le numéro est trouvé (optimisation)
                if PATTERN.search("\n".join(text_parts)):
                    break
    except Exception as e:
        raise RuntimeError(f"pdfplumber: {e}")
    return "\n".join(text_parts)


def extract_text_pypdf(pdf_path: Path) -> str:
    """Extraction de texte via pypdf (fallback)."""
    text_parts = []
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
            if PATTERN.search("\n".join(text_parts)):
                break
    except Exception as e:
        raise RuntimeError(f"pypdf: {e}")
    return "\n".join(text_parts)


def extract_text(pdf_path: Path) -> str:
    """Essaie pdfplumber en premier, puis pypdf en fallback."""
    if HAS_PDFPLUMBER:
        try:
            return extract_text_pdfplumber(pdf_path)
        except RuntimeError as e:
            print(f"  ⚠  pdfplumber a échoué ({e}), tentative avec pypdf…")
    if HAS_PYPDF:
        return extract_text_pypdf(pdf_path)
    return ""


def find_demande_number(text: str) -> str | None:
    """Retourne le premier numéro de demande trouvé dans le texte, ou None."""
    match = PATTERN.search(text)
    return match.group(0) if match else None


def build_new_name(demande_number: str, suffix: int = 0) -> str:
    """Construit le nom de fichier cible (avec suffixe si doublon)."""
    base = f"{demande_number}.pdf"
    if suffix == 0:
        return base
    return f"{demande_number}_{suffix}.pdf"


def rename_pdfs(folder: Path, dry_run: bool = False, recursive: bool = False):
    """Parcourt le dossier et renomme les PDFs selon leur numéro de demande."""
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted(folder.glob(pattern))

    if not pdf_files:
        print(f"Aucun fichier PDF trouvé dans : {folder}")
        return

    print(f"{'[SIMULATION] ' if dry_run else ''}Traitement de {len(pdf_files)} fichier(s)…\n")

    stats = {"renamed": 0, "skipped": 0, "not_found": 0, "errors": 0}
    used_names: dict[str, Path] = {}  # garde une trace des noms déjà attribués

    for pdf_path in pdf_files:
        print(f"📄 {pdf_path.name}")
        try:
            text = extract_text(pdf_path)
        except Exception as e:
            print(f"  ✗ Erreur lors de la lecture : {e}\n")
            stats["errors"] += 1
            continue

        demande_number = find_demande_number(text)

        if not demande_number:
            print(f"  ✗ Numéro de demande introuvable (format Dxxxxx_xxxxx)\n")
            stats["not_found"] += 1
            continue

        print(f"  ✔ Numéro trouvé : {demande_number}")

        # Gestion des doublons
        suffix = 0
        new_name = build_new_name(demande_number, suffix)
        target_path = pdf_path.parent / new_name
        while target_path in used_names.values() or (target_path.exists() and target_path != pdf_path):
            suffix += 1
            new_name = build_new_name(demande_number, suffix)
            target_path = pdf_path.parent / new_name

        if pdf_path.name == new_name:
            print(f"  — Fichier déjà nommé correctement, ignoré.\n")
            stats["skipped"] += 1
            continue

        print(f"  → {'Serait renommé' if dry_run else 'Renommé'} : {new_name}")
        if not dry_run:
            pdf_path.rename(target_path)
        used_names[demande_number] = target_path
        stats["renamed"] += 1
        print()

    print("─" * 50)
    print(f"Résumé :")
    print(f"  ✔ Renommés     : {stats['renamed']}")
    print(f"  — Ignorés      : {stats['skipped']}")
    print(f"  ✗ Sans numéro  : {stats['not_found']}")
    print(f"  ✗ Erreurs      : {stats['errors']}")
    if dry_run:
        print("\n⚠  Mode simulation — aucun fichier n'a été modifié.")


def main():
    parser = argparse.ArgumentParser(
        description="Renomme les PDFs selon leur numéro de demande (format Dxxxxx_xxxxx)."
    )
    parser.add_argument(
        "dossier",
        type=Path,
        help="Dossier contenant les fichiers PDF à traiter"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule les renommages sans modifier les fichiers"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Traite également les sous-dossiers"
    )
    args = parser.parse_args()

    if not args.dossier.is_dir():
        print(f"Erreur : '{args.dossier}' n'est pas un dossier valide.")
        sys.exit(1)

    rename_pdfs(args.dossier, dry_run=args.dry_run, recursive=args.recursive)


if __name__ == "__main__":
    main()
