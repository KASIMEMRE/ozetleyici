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
