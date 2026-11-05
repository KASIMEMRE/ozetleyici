"""Dosyadan metin okuma: .txt, .md ve .pdf."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

DESTEKLENEN_UZANTILAR = {".txt", ".md", ".pdf"}

# Metin dosyalarını bu sırayla deneriz. "cp1254", eski Windows programlarının
# Türkçe için kullandığı kodlamadır; UTF-8 olmayan dosyalar genelde budur.
METIN_KODLAMALARI = ("utf-8-sig", "cp1254")

# Çok büyük dosyalar hem belleği hem API bütçesini tüketir.
EN_BUYUK_DOSYA_MB = 50


class OkumaHatasi(Exception):
    """Dosya okunamadığında kullanıcıya gösterilecek anlamlı hata."""


def metni_oku(yol: Path) -> str:
    """Dosyayı uzantısına göre okuyup temizlenmiş metni döndürür."""
    if not yol.exists():
        raise OkumaHatasi(f"Dosya bulunamadı: {yol}")
    if not yol.is_file():
        raise OkumaHatasi(f"Bu bir dosya değil: {yol}")

    uzanti = yol.suffix.lower()
    if uzanti not in DESTEKLENEN_UZANTILAR:
        desteklenen = ", ".join(sorted(DESTEKLENEN_UZANTILAR))
        raise OkumaHatasi(f"Desteklenmeyen dosya türü: {uzanti} (desteklenenler: {desteklenen})")

    boyut_mb = yol.stat().st_size / 1_000_000
    if boyut_mb > EN_BUYUK_DOSYA_MB:
        raise OkumaHatasi(f"Dosya çok büyük: {boyut_mb:.0f} MB (sınır {EN_BUYUK_DOSYA_MB} MB).")

    metin = _pdf_oku(yol) if uzanti == ".pdf" else _metin_dosyasi_oku(yol)
    metin = _temizle(metin)

    if not metin:
        ipucu = " Taranmış (görüntü) bir PDF olabilir; bunun için OCR gerekir." if uzanti == ".pdf" else ""
        raise OkumaHatasi(f"Dosyadan hiç metin çıkmadı: {yol}.{ipucu}")
    return metin


def _metin_dosyasi_oku(yol: Path) -> str:
    ham = yol.read_bytes()
    for kodlama in METIN_KODLAMALARI:
        try:
            return ham.decode(kodlama)
        except UnicodeDecodeError:
            continue
    raise OkumaHatasi(f"Dosyanın karakter kodlaması çözülemedi: {yol}")


def _pdf_oku(yol: Path) -> str:
    try:
        okuyucu = PdfReader(yol)
        if okuyucu.is_encrypted:
            raise OkumaHatasi(f"PDF şifreli, okunamıyor: {yol}")
        sayfalar = [sayfa.extract_text() or "" for sayfa in okuyucu.pages]
    except PdfReadError as hata:
        raise OkumaHatasi(f"PDF bozuk veya okunamıyor: {yol} ({hata})") from hata
    return "\n\n".join(sayfalar)


def _temizle(metin: str) -> str:
    # PDF'lerde "ş" bazen "s" + birleştirici işaret olarak iki karakter gelir.
    # NFC normalleştirmesi bunları tek karaktere birleştirir.
    metin = unicodedata.normalize("NFC", metin)
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")
    satirlar = [satir.rstrip() for satir in metin.split("\n")]
    temiz = "\n".join(satirlar)
    while "\n\n\n" in temiz:
        temiz = temiz.replace("\n\n\n", "\n\n")
    return temiz.strip()
