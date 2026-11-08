"""PDF okuyucu: metinli sayfaları doğrudan, taranmış sayfaları OCR ile okur."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .gorsel import resmi_oku
from .temel import OcrAyari, OkumaHatasi, OkumaSonucu, imzayi_dogrula, metni_temizle

# Bir sayfada bundan az harf varsa taranmış (görüntü) sayfa kabul edilir.
TARANMIS_ESIK = 25
OCR_COZUNURLUK = 200  # dpi; Tesseract için iyi bir denge


def pdf_oku(veri: bytes, ad: str, ocr: OcrAyari) -> OkumaSonucu:
    imzayi_dogrula(veri, "pdf", ad)
    try:
        okuyucu = PdfReader(io.BytesIO(veri))
        if okuyucu.is_encrypted:
            raise OkumaHatasi(f"{ad}: PDF şifreli, okunamıyor.")
        sayfalar = [sayfa.extract_text() or "" for sayfa in okuyucu.pages]
    except PdfReadError as hata:
        raise OkumaHatasi(f"{ad}: PDF bozuk veya okunamıyor ({hata}).") from hata

    notlar: list[str] = [f"{len(sayfalar)} sayfa."]
    taranmis = [i for i, s in enumerate(sayfalar) if sum(c.isalpha() for c in s) < TARANMIS_ESIK]
    ocr_sayisi = 0
    gonderilen = 0

    if taranmis and ocr.kip != "kapali":
        hedef = taranmis[: ocr.en_fazla_sayfa]
        if len(taranmis) > len(hedef):
            notlar.append(f"{len(taranmis)} taranmış sayfanın yalnızca ilk {len(hedef)} tanesi OCR ile okundu.")
        if ocr.kip == "gemini" and ocr.on_kontrol:
            ocr.on_kontrol(len(hedef))  # her sayfa bir API isteği
        import pypdfium2 as pdfium

        belge = pdfium.PdfDocument(veri)
        try:
            for i in hedef:
                resim = belge[i].render(scale=OCR_COZUNURLUK / 72).to_pil().convert("RGB")
                sayfalar[i] = resmi_oku(resim, ocr, f"{ad} sayfa {i + 1}")
                ocr_sayisi += 1
                if ocr.kip == "gemini":
                    gonderilen += 1
        finally:
            belge.close()
        yontem = "Gemini (görüntü sağlayıcıya gönderildi)" if ocr.kip == "gemini" else "yerel Tesseract"
        notlar.append(f"{ocr_sayisi} taranmış sayfa OCR ile okundu: {yontem}.")
    elif taranmis:
        notlar.append(f"{len(taranmis)} sayfa taranmış görünüyor ama OCR kapalı; bu sayfalar boş kaldı.")

    metin = metni_temizle("\n\n".join(f"[Sayfa {i + 1}]\n{s}" if s.strip() else "" for i, s in enumerate(sayfalar)), notlar)
    if not metin:
        raise OkumaHatasi(f"{ad}: dosyadan hiç metin çıkmadı. Taranmış bir PDF olabilir; bunun için OCR gerekir.")
    return OkumaSonucu(metin, "pdf", notlar, ocr_sayisi, gonderilen)
