from pathlib import Path

import pytest

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


def test_pdf_turkce_ve_cok_sayfa():
    metin = metni_oku(VERI / "ornek.pdf")
    assert "Kişisel Verilerin Korunması" in metin
    assert "ğüşıöç İ" in metin
    assert "İkinci sayfa" in metin


def test_bos_pdf_anlamli_hata():
    with pytest.raises(OkumaHatasi, match="OCR"):
        metni_oku(VERI / "bos.pdf")


def test_olmayan_dosya(tmp_path):
    with pytest.raises(OkumaHatasi, match="bulunamadı"):
        metni_oku(tmp_path / "yok.pdf")


def test_desteklenmeyen_uzanti(tmp_path):
    dosya = tmp_path / "a.docx"
    dosya.write_bytes(b"x")
    with pytest.raises(OkumaHatasi, match="Desteklenmeyen"):
        metni_oku(dosya)
