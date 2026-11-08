"""Gerçek LLM API'sine bir istek atar. Varsayılan olarak ATLANIR.

Çalıştırmak için (.env dolu olmalı; ücretli katmanda küçük bir maliyeti olur):
    PowerShell:  $env:OZETLEYICI_GERCEK_TEST=1; python -m pytest -m gercek_api
Amaç: sağlayıcı biçimini değiştirirse sahte sunucu testlerinin yakalayamadığını yakalamak.
"""

import os

import pytest

pytestmark = pytest.mark.gercek_api


@pytest.mark.skipif(os.getenv("OZETLEYICI_GERCEK_TEST") != "1", reason="OZETLEYICI_GERCEK_TEST=1 değil")
def test_gercek_saglayici_kisa_ozet():
    from ozetleyici.ayarlar import ayarlari_yukle
    from ozetleyici.llm import LLMIstemcisi, UretimAyarlari
    from ozetleyici.ozetle import ozetle

    istemci = LLMIstemcisi(ayarlari_yukle())
    gelen = []
    sonuc = ozetle(
        "Şirket, 1 Ocak 2027'den itibaren çalışanlara haftada üç gün uzaktan çalışma hakkı tanır.",
        istemci, UretimAyarlari(max_token=512), uzunluk="kisa", parca_gelince=gelen.append,
    )
    assert sonuc.ozet and "".join(gelen).strip() == sonuc.ozet
    assert "2027" in sonuc.ozet or "üç" in sonuc.ozet


CUMLE = "Bugünkü toplantıda bütçe onaylandı ve proje teslim tarihi mart ayına ertelendi."
ANAHTAR_KELIMELER = ("bütçe", "onaylandı", "proje", "teslim", "mart", "ertelendi")


@pytest.mark.skipif(not os.getenv("OZETLEYICI_SES_DOSYASI"), reason="OZETLEYICI_SES_DOSYASI verilmedi")
def test_gercek_whisper_turkce(capsys):
    """Kendi sesinle şu cümleyi kaydet ve dosya yolunu ver:

        "Bugünkü toplantıda bütçe onaylandı ve proje teslim tarihi mart ayına ertelendi."

    PowerShell:
        $env:OZETLEYICI_SES_DOSYASI="C:\\Users\\Emre\\Documents\\Ses Kayıtları\\kayit.m4a"
        python -m pytest -m gercek_api -k whisper -s
    İlk çalıştırmada model (~500 MB) indirilir. Ses bilgisayardan çıkmaz.
    """
    from pathlib import Path

    from ozetleyici.ayarlar import whisper_modeli
    from ozetleyici.okuyucular import OcrAyari, belgeyi_oku

    yol = Path(os.environ["OZETLEYICI_SES_DOSYASI"])
    sonuc = belgeyi_oku(yol.read_bytes(), yol.name, OcrAyari(ses_kipi="yerel", whisper_modeli=whisper_modeli()))
    metin = sonuc.metin.casefold()
    bulunan = [k for k in ANAHTAR_KELIMELER if k.casefold() in metin]
    with capsys.disabled():
        print(f"\n--- Whisper çıktısı ({sonuc.ses_suresi_sn} sn) ---\n{sonuc.metin}\n"
              f"--- Bulunan anahtar kelimeler: {len(bulunan)}/{len(ANAHTAR_KELIMELER)}: {', '.join(bulunan)}")
    assert len(bulunan) >= 4, "Kayıt net değil ya da model Türkçeyi yeterince iyi tanımadı"
