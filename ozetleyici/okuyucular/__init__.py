"""Belge okuyucuları: dosya türüne göre doğru okuyucuyu seçer.

Tüm okuyucular dosyayı diskten değil bellekten (bytes) okur. Böylece web
uygulamasında yüklenen dosya hiçbir zaman diske yazılmaz.
"""

from __future__ import annotations

from .gorsel import resmi_ac, resmi_oku, tesseract_yolu
from .ofis import powerpoint_oku, word_oku
from .pdf import pdf_oku
from .tablo import csv_oku, excel_oku
from .temel import OcrAyari, OkumaHatasi, OkumaSonucu, imzayi_dogrula, metin_kodunu_coz, metni_temizle

TURLER = {
    ".txt": "metin", ".md": "metin", ".csv": "csv",
    ".pdf": "pdf",
    ".docx": "word", ".pptx": "powerpoint", ".xlsx": "excel", ".xlsm": "excel",
    ".png": "gorsel", ".jpg": "gorsel", ".jpeg": "gorsel",
}
ESKI_BICIMLER = {".doc": ".docx", ".xls": ".xlsx", ".ppt": ".pptx"}
DESTEKLENEN_UZANTILAR = set(TURLER)

__all__ = ["OcrAyari", "OkumaHatasi", "OkumaSonucu", "belgeyi_oku", "tesseract_yolu", "DESTEKLENEN_UZANTILAR"]


def uzantiyi_al(ad: str) -> str:
    nokta = ad.rfind(".")
    return ad[nokta:].lower() if nokta != -1 else ""


def belgeyi_oku(veri: bytes, ad: str, ocr: OcrAyari | None = None) -> OkumaSonucu:
    """Dosya içeriğini (bytes) ve adını alıp temizlenmiş metni döndürür."""
    ocr = ocr or OcrAyari()
    uzanti = uzantiyi_al(ad)
    if uzanti in ESKI_BICIMLER:
        raise OkumaHatasi(
            f"{ad}: eski {uzanti} biçimi desteklenmiyor. Dosyayı Office'te açıp "
            f"'Farklı Kaydet' ile {ESKI_BICIMLER[uzanti]} olarak kaydet."
        )
    tur = TURLER.get(uzanti)
    if tur is None:
        desteklenen = ", ".join(sorted(DESTEKLENEN_UZANTILAR))
        raise OkumaHatasi(f"Desteklenmeyen dosya türü: {uzanti or '(uzantı yok)'} (desteklenenler: {desteklenen})")
    if not veri:
        raise OkumaHatasi(f"{ad}: dosya boş.")

    if tur == "metin":
        notlar: list[str] = []
        sonuc = OkumaSonucu(metni_temizle(metin_kodunu_coz(veri, ad), notlar), "metin", notlar)
    elif tur == "csv":
        sonuc = csv_oku(veri, ad)
    elif tur == "pdf":
        sonuc = pdf_oku(veri, ad, ocr)
    elif tur == "word":
        sonuc = word_oku(veri, ad)
    elif tur == "powerpoint":
        sonuc = powerpoint_oku(veri, ad)
    elif tur == "excel":
        sonuc = excel_oku(veri, ad)
    else:  # gorsel
        imzayi_dogrula(veri, "png" if uzanti == ".png" else "jpg", ad)
        resim = resmi_ac(veri, ad)
        notlar = []
        metin = metni_temizle(resmi_oku(resim, ocr, ad), notlar)
        yontem = "Gemini (görüntü sağlayıcıya gönderildi)" if ocr.kip == "gemini" else "yerel Tesseract"
        notlar.insert(0, f"Görüntü OCR ile okundu: {yontem}.")
        sonuc = OkumaSonucu(metin, "gorsel", notlar, 1, 1 if ocr.kip == "gemini" else 0)

    if not sonuc.metin.strip():
        raise OkumaHatasi(f"{ad}: dosyadan hiç metin çıkmadı.")
    return sonuc
