"""Depoya gizli anahtar girmesini engelleyen basit tarayıcı.

Kullanım:
    python scripts/gizli_tara.py            # Git'in izlediği tüm dosyaları tara
    python scripts/gizli_tara.py --staged   # Yalnızca commit'e hazırlanan içeriği tara (commit kancası)

Bulursa çıkış kodu 1 döner ve commit engellenir. Bulunan değeri ekrana basmaz,
yalnızca ilk 4 karakterini gösterir.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

DESENLER = {
    "Google API anahtarı": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Google API anahtarı (yeni biçim)": re.compile(r"AQ\.[0-9A-Za-z_\-]{30,}"),
    "Anthropic API anahtarı": re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"),
    "OpenAI API anahtarı": re.compile(r"sk-(?:proj-|svcacct-)?(?!ant-)[0-9A-Za-z_\-]{20,}"),
    "GitHub token'ı": re.compile(r"gh[pousr]_[0-9A-Za-z]{36,}"),
    "Özel anahtar (private key)": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # Yorum satırı olmayan ve yer tutucu dışında değer taşıyan LLM_API_KEY satırı.
    "Doldurulmuş LLM_API_KEY": re.compile(
        r"^[ \t]*LLM_API_KEY[ \t]*=[ \t]*(?!buraya-anahtarini-yaz[ \t]*$|ollama[ \t]*$)\S+",
        re.MULTILINE,
    ),
}

# Hiçbir koşulda depoya girmemesi gereken dosya adları.
YASAK_DOSYA = re.compile(r"(^|/)\.env(\.(?!example$)[^/]+)?$")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=KOK, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def _dosyalar(staged: bool) -> list[tuple[str, str]]:
    """(yol, içerik) çiftleri. --staged modunda çalışma kopyası değil, commit'e girecek içerik okunur."""
    if staged:
        yollar = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
        okuyucu = lambda yol: _git("show", f":{yol}")
    else:
        try:
            yollar = _git("ls-files").splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):
            yollar = [str(p.relative_to(KOK)).replace("\\", "/") for p in KOK.rglob("*")
                      if p.is_file() and not {".git", ".venv", "__pycache__"} & set(p.parts)]
        okuyucu = lambda yol: (KOK / yol).read_text(encoding="utf-8", errors="ignore")

    sonuc = []
    for yol in yollar:
        if yol.endswith((".pdf", ".png", ".jpg", ".pyc")):
            sonuc.append((yol, ""))  # ikili dosya: yalnızca adını kontrol et
            continue
        try:
            sonuc.append((yol, okuyucu(yol)))
        except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
            sonuc.append((yol, ""))
    return sonuc


def tara(dosyalar: list[tuple[str, str]]) -> list[str]:
    """Bulguları 'yol:satır  tür  (değerin başı…)' biçiminde döndürür."""
    bulgular = []
    for yol, icerik in dosyalar:
        if YASAK_DOSYA.search(yol):
            bulgular.append(f"{yol}  bu dosya depoya hiç girmemeli (gizli ayar dosyası)")
        for tur, desen in DESENLER.items():
            for eslesme in desen.finditer(icerik):
                satir = icerik.count("\n", 0, eslesme.start()) + 1
                bulgular.append(f"{yol}:{satir}  {tur}  ({eslesme.group(0).strip()[:4]}…)")
    return bulgular


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    bulgular = tara(_dosyalar(staged="--staged" in argv))
    if not bulgular:
        print("[gizli-tara] Temiz: gizli anahtar bulunmadı.")
        return 0
    print("[gizli-tara] DURDURULDU. Gizli bilgi olabilecek şeyler bulundu:", file=sys.stderr)
    for b in bulgular:
        print(f"  - {b}", file=sys.stderr)
    print("Anahtarlar yalnızca .env dosyasında durmalı. Dosyayı düzeltip yeniden 'git add' yap.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
