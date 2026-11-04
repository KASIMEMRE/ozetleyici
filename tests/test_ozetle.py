from ozetleyici.llm import LLMCevabi, UretimAyarlari
from ozetleyici.ozetle import maliyet_hesapla, metni_parcala, ozetle


class SahteIstemci:
    """Gerçek API yerine geçen, çağrıları kaydeden sahte istemci."""

    model = "sahte-model"

    def __init__(self):
        self.cagrilar = []

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None):
        self.cagrilar.append((sistem, kullanici))
        metin = f"özet-{len(self.cagrilar)}"
        if parca_gelince:
            parca_gelince(metin)
        return LLMCevabi(metin=metin, girdi_token=100, cikti_token=10, deneme_sayisi=1)


def test_kisa_metin_tek_istek():
    istemci = SahteIstemci()
    sonuc = ozetle("Kısa bir belge.", istemci, UretimAyarlari())
    assert sonuc.istek_sayisi == 1
    assert sonuc.ozet == "özet-1"
    assert "<belge>" in istemci.cagrilar[0][1]


def test_uzun_metin_parcalanip_birlestirilir():
    istemci = SahteIstemci()
    metin = "\n\n".join(["paragraf " * 500] * 6)  # ~27.000 karakter
    sonuc = ozetle(metin, istemci, UretimAyarlari())
    assert sonuc.parca_sayisi >= 2
    assert sonuc.istek_sayisi == sonuc.parca_sayisi + 1  # her parça + birleştirme
    assert "Parça 1" in istemci.cagrilar[-1][1]
    assert sonuc.girdi_token == 100 * sonuc.istek_sayisi


def test_parcalar_metni_kaybetmez():
    metin = "\n\n".join(f"P{i} " + "x" * 3000 for i in range(10))
    parcalar = metni_parcala(metin, boyut=8000)
    assert all(len(p) <= 8000 for p in parcalar)
    assert "".join(parcalar).replace("\n", "") == metin.replace("\n", "")


def test_cok_uzun_tek_paragraf_bolunur():
    parcalar = metni_parcala("a" * 25_000, boyut=10_000)
    assert [len(p) for p in parcalar] == [10_000, 10_000, 5_000]


def test_akis_geri_cagirimi():
    gelenler = []
    ozetle("Belge", SahteIstemci(), UretimAyarlari(), parca_gelince=gelenler.append)
    assert gelenler == ["özet-1"]


def test_maliyet():
    assert maliyet_hesapla(1_000_000, 0, 0.30, 2.50) == 0.30
    assert maliyet_hesapla(1000, 500, 0.30, 2.50) == 0.00155
    assert maliyet_hesapla(1000, 500, None, 2.50) is None
