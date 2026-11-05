from pathlib import Path

import pytest

from ozetleyici import okuyucu
from ozetleyici.okuyucu import OkumaHatasi, metni_oku

VERI = Path(__file__).parent / "veri"


def test_utf8_metin(tmp_path):
    dosya = tmp_path / "a.txt"
    dosya.write_text("Çalışan ğüşıöç İ", encoding="utf-8")
    assert metni_oku(dosya) == "Çalışan ğüşıöç İ"


def test_eski_windows_kodlamasi_cp1254(tmp_path):
    dosya = tmp_path / "eski.txt"
    dosya.write_bytes("Şirket ğüşıöç".encode("cp1254"))
    assert metni_oku(dosya) == "Şirket ğüşıöç"


def test_ayrik_karakterler_birlestirilir(tmp_path):
    dosya = tmp_path / "nfd.txt"
    dosya.write_text("şirket", encoding="utf-8")  # "s" + birleştirici çengel
    assert metni_oku(dosya) == "şirket"


def test_windows_satir_sonlari(tmp_path):
    dosya = tmp_path / "crlf.txt"
    dosya.write_bytes("bir\r\niki\r\n\r\n\r\n\r\nüç".encode("utf-8"))
    assert metni_oku(dosya) == "bir\niki\n\nüç"


def test_pdf_turkce_ve_cok_sayfa():
    metin = metni_oku(VERI / "ornek.pdf")
    assert "Kişisel Verilerin Korunması" in metin
    assert "ğüşıöç İ" in metin
    assert "İkinci sayfa" in metin


def test_bos_pdf_anlamli_hata():
    with pytest.raises(OkumaHatasi, match="OCR"):
        metni_oku(VERI / "bos.pdf")


def test_bozuk_pdf(tmp_path):
    dosya = tmp_path / "bozuk.pdf"
    dosya.write_bytes(b"bu bir pdf degil")
    with pytest.raises(OkumaHatasi):
        metni_oku(dosya)


def test_olmayan_dosya(tmp_path):
    with pytest.raises(OkumaHatasi, match="bulunamadı"):
        metni_oku(tmp_path / "yok.pdf")


def test_klasor_verilirse(tmp_path):
    with pytest.raises(OkumaHatasi, match="dosya değil"):
        metni_oku(tmp_path)


def test_desteklenmeyen_uzanti(tmp_path):
    dosya = tmp_path / "a.docx"
    dosya.write_bytes(b"x")
    with pytest.raises(OkumaHatasi, match="Desteklenmeyen"):
        metni_oku(dosya)


def test_cok_buyuk_dosya(tmp_path, monkeypatch):
    monkeypatch.setattr(okuyucu, "EN_BUYUK_DOSYA_MB", 0.000001)
    dosya = tmp_path / "a.txt"
    dosya.write_text("biraz metin", encoding="utf-8")
    with pytest.raises(OkumaHatasi, match="çok büyük"):
        metni_oku(dosya)
