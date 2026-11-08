"""Diskteki bir dosyayı okumak için kısayol (komut satırı aracı bunu kullanır).

Asıl okuma mantığı `okuyucular` paketinde; bu modül dosyayı diskten okuyup oraya verir.
"""

from __future__ import annotations

from pathlib import Path

from .okuyucular import DESTEKLENEN_UZANTILAR, MEDYA_UZANTILARI, OcrAyari, OkumaHatasi, OkumaSonucu, belgeyi_oku

__all__ = ["DESTEKLENEN_UZANTILAR", "OcrAyari", "OkumaHatasi", "OkumaSonucu", "belge_dosyasini_oku", "metni_oku"]

# Çok büyük dosyalar hem belleği hem API bütçesini tüketir.
EN_BUYUK_DOSYA_MB = 50
EN_BUYUK_MEDYA_MB = 200


def belge_dosyasini_oku(yol: Path, ocr: OcrAyari | None = None) -> OkumaSonucu:
    if not yol.exists():
        raise OkumaHatasi(f"Dosya bulunamadı: {yol}")
    if not yol.is_file():
        raise OkumaHatasi(f"Bu bir dosya değil: {yol}")
    boyut_mb = yol.stat().st_size / 1_000_000
    sinir = EN_BUYUK_MEDYA_MB if yol.suffix.lower() in MEDYA_UZANTILARI else EN_BUYUK_DOSYA_MB
    if boyut_mb > sinir:
        raise OkumaHatasi(f"Dosya çok büyük: {boyut_mb:.0f} MB (sınır {sinir} MB).")
    return belgeyi_oku(yol.read_bytes(), yol.name, ocr)


def metni_oku(yol: Path, ocr: OcrAyari | None = None) -> str:
    """Dosyayı okuyup yalnızca temizlenmiş metni döndürür."""
    return belge_dosyasini_oku(yol, ocr).metin
