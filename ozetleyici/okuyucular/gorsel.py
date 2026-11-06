"""Görsellerden ve taranmış sayfalardan metin okuma (OCR)."""

from __future__ import annotations

import io
import os
import shutil
import warnings
from pathlib import Path

from PIL import Image

from .temel import OcrAyari, OkumaHatasi

# Piksel bombası koruması: küçük bir PNG açılınca devasa bir görüntüye dönüşmesin.
Image.MAX_IMAGE_PIXELS = 40_000_000
GEMINI_EN_BUYUK_KENAR = 2000  # Gemini'ye gönderilen görüntü bu boyuta küçültülür (token tasarrufu)

WINDOWS_TESSERACT = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
]

KURULUM_IPUCU = (
    "Tesseract bulunamadı. Windows için: https://github.com/UB-Mannheim/tesseract/wiki adresinden "
    "kurucuyu indir, kurulumda 'Additional language data' altından Turkish'i seç. "
    "Farklı bir yere kurduysan .env dosyasına TESSERACT_YOLU=C:\\...\\tesseract.exe yaz."
)


def tesseract_yolu() -> str | None:
    """Tesseract programının yolunu bulur; yoksa None."""
    ozel = os.environ.get("TESSERACT_YOLU", "").strip().strip('"')
    if ozel:
        return ozel if Path(ozel).is_file() else None
    bulunan = shutil.which("tesseract")
    if bulunan:
        return bulunan
    for aday in WINDOWS_TESSERACT:
        if aday.is_file():
            return str(aday)
    return None


def resmi_ac(veri: bytes, ad: str) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            resim = Image.open(io.BytesIO(veri))
            resim.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as hata:
        raise OkumaHatasi(f"{ad}: görüntü çok büyük (piksel bombası olabilir); reddedildi.") from hata
    except Exception as hata:
        raise OkumaHatasi(f"{ad}: görüntü açılamadı ({type(hata).__name__}).") from hata
    return resim.convert("RGB")


def resmi_oku(resim: Image.Image, ocr: OcrAyari, ad: str) -> str:
    """Tek bir görüntüdeki metni ayara göre yerel Tesseract veya Gemini ile okur."""
    if ocr.kip == "kapali":
        raise OkumaHatasi(f"{ad}: görüntüden metin okumak için OCR gerekir, ama OCR kapalı.")
    if ocr.kip == "gemini":
        if ocr.gorsel_okuyucu is None:
            raise OkumaHatasi("Gemini OCR seçildi ama LLM istemcisi verilmedi.")
        kopya = resim.copy()
        kopya.thumbnail((GEMINI_EN_BUYUK_KENAR, GEMINI_EN_BUYUK_KENAR))
        tampon = io.BytesIO()
        kopya.save(tampon, format="PNG")
        return ocr.gorsel_okuyucu(tampon.getvalue())
    return _tesseract(resim, ocr.dil, ad)


def _tesseract(resim: Image.Image, dil: str, ad: str) -> str:
    import pytesseract

    yol = tesseract_yolu()
    if yol is None:
        raise OkumaHatasi(f"{ad}: {KURULUM_IPUCU}")
    pytesseract.pytesseract.tesseract_cmd = yol
    try:
        return pytesseract.image_to_string(resim, lang=dil, timeout=120)
    except pytesseract.TesseractError as hata:
        if "Failed loading language" in str(hata) or "traineddata" in str(hata):
            raise OkumaHatasi(
                f"Tesseract kurulu ama '{dil}' dil paketi yok. Kurucuyu yeniden çalıştırıp Turkish'i seç "
                "veya tur.traineddata dosyasını Tesseract'ın tessdata klasörüne koy."
            ) from hata
        raise OkumaHatasi(f"{ad}: OCR başarısız ({hata}).") from hata
    except RuntimeError as hata:  # pytesseract zaman aşımında RuntimeError fırlatır
        raise OkumaHatasi(f"{ad}: OCR zaman aşımına uğradı.") from hata
