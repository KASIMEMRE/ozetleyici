"""Soru-cevap değerlendirmesi (eval): set dosyası, ölçümler, hakem ve komut satırı."""

import json
from pathlib import Path

import pytest

from ozetleyici import degerlendir as d
from ozetleyici.llm import IstekButcesi, LLMCevabi
from ozetleyici.soru import BULUNAMADI, BelgeIndeksi, soruyu_cevapla
from tests.test_soru import kelime_vektoru

ANAHTAR = "gercek-gibi-anahtar-987654"
BELGE = """Seyahat Kuralları

Yurt içi seyahatte günlük yemek harcırahı 750 TL'dir.

Konaklama için gecelik üst sınır Ankara'da 4.000 TL, diğer illerde 2.500 TL'dir.

Masraflar harcama tarihinden itibaren 30 gün içinde sisteme girilir.

Kaybolan cihaz 24 saat içinde bilgi güvenliği ekibine bildirilir."""

SET = {
    "belge": "belge.txt",
    "sorular": [
        {"soru": "Ankara'da otel için gecelik sınır ne kadar?", "beklenen": "4.000 TL",
         "kanit": "Ankara'da 4.000 TL", "anahtar": ["4.000"]},
        {"soru": "Masrafları ne zamana kadar girmeliyim?", "beklenen": "30 gün içinde",
         "kanit": "30 gün içinde sisteme", "anahtar": ["30"]},
        {"soru": "Evlilik izni kaç gün?", "cevap_yok": True},
    ],
}


def set_yaz(tmp_path, veri=SET, belge=BELGE):
    (tmp_path / "belge.txt").write_text(belge, encoding="utf-8")
    yol = tmp_path / "set.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return yol


class SahteIstemci:
    """Soruya göre hazır cevap veren, hakem çağrılarını ayrı sayan sahte istemci."""

    def __init__(self, cevaplar, hakem_karari='{"dogruluk": "dogru", "dayanak": "tam", "gerekce": "ok"}',
                 butce=None, model="sahte"):
        self.cevaplar, self.hakem_karari, self.butce, self.model = cevaplar, hakem_karari, butce, model
        self.gomme_token = 0
        self.gom_cagrilari: list[int] = []
        self.cevap_cagrilari = 0
        self.hakem_cagrilari = 0

    def gom(self, metinler, model):
        if self.butce:
            self.butce.harca()
        self.gom_cagrilari.append(len(metinler))
        return [kelime_vektoru(m) for m in metinler]

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
        if self.butce:
            self.butce.harca()
        if sistem == d.HAKEM_TALIMATI:
            self.hakem_cagrilari += 1
            assert uretim.temperature == 0  # hakem tutarlı olsun
            return LLMCevabi(self.hakem_karari, 10, 10, 1, model=self.model)
        self.cevap_cagrilari += 1
        soru = kullanici.rsplit("Soru: ", 1)[1]
        return LLMCevabi(self.cevaplar.get(soru, BULUNAMADI), 10, 10, 1, model=self.model)


IYI_CEVAPLAR = {
    "Ankara'da otel için gecelik sınır ne kadar?": "Gecelik en fazla 4.000 TL [1].",
    "Masrafları ne zamana kadar girmeliyim?": "Harcamadan itibaren 30 gün içinde [1].",
}


# ---------------------------------------------------------------- set dosyası

def test_set_yuklenir_ve_belge_yolu_sete_gore(tmp_path):
    belge, _, ornekler = d.seti_yukle(set_yaz(tmp_path))
    assert belge == tmp_path / "belge.txt"
    assert [o.cevap_yok for o in ornekler] == [False, False, True]
    assert ornekler[0].anahtar == ["4.000"]


@pytest.mark.parametrize("soru,mesaj", [
    ({"soru": "Kaç?"}, "beklenen"),
    ({"soru": "Kaç?", "cevap_yok": True, "kanit": "x"}, "cevap_yok"),
    ({"soru": "", "beklenen": "x"}, "soru"),
    ({"soru": "Kaç?", "beklenen": "x", "anahtar": "4.000"}, "anahtar"),
])
def test_hatali_set_anlamli_hata(tmp_path, soru, mesaj):
    with pytest.raises(d.SetHatasi, match=mesaj):
        d.seti_yukle(set_yaz(tmp_path, {"belge": "belge.txt", "sorular": [soru]}))


def test_bozuk_json_satir_numarasi_verir(tmp_path):
    yol = tmp_path / "set.json"
    yol.write_text('{"belge": "b.txt",\n "sorular": [}', encoding="utf-8")
    with pytest.raises(d.SetHatasi, match="satır 2"):
        d.seti_yukle(yol)


def test_belgede_olmayan_kanit_yakalanir(tmp_path):
    _, _, ornekler = d.seti_yukle(set_yaz(tmp_path))
    ornekler[0].kanit = "Ankara'da 5.000 TL"
    with pytest.raises(d.SetHatasi, match="1. sorunun kanıtı"):
        d.kanitlari_dogrula(ornekler, BELGE)


def test_ornek_set_gecerli():
    """Depodaki örnek set: her kanıt belgede birebir geçiyor."""
    kok = Path(__file__).resolve().parent.parent / "degerlendirme" / "calisan_el_kitabi.json"
    belge, _, ornekler = d.seti_yukle(kok)
    d.kanitlari_dogrula(ornekler, belge.read_text(encoding="utf-8"))
    assert sum(o.cevap_yok for o in ornekler) >= 3


# ---------------------------------------------------------------- kurallı kontroller

def test_anahtar_sayilar_bicimden_bagimsiz():
    assert d.anahtarlar_var_mi("Gecelik 4000 TL.", ["4.000"])
    assert d.anahtarlar_var_mi("Gecelik 4.000 TL.", ["4.000"])
    assert not d.anahtarlar_var_mi("16 hafta", ["6"])  # "6", "16"nın içinde sayılmaz
    assert not d.anahtarlar_var_mi("2.500 TL", ["4.000"])


def test_reddetme_ve_gecersiz_atif():
    assert d.reddetti_mi(BULUNAMADI)
    assert d.reddetti_mi("Üzgünüm, belgede bu sorunun cevabını bulamadım.")
    assert not d.reddetti_mi("4.000 TL [1].")
    assert d.gecersiz_atiflar("Bilgi [1][7] ve [0].", 5) == [0, 7]


@pytest.mark.parametrize("metin,dogruluk,dayanak", [
    ('{"dogruluk": "dogru", "dayanak": "tam", "gerekce": "x"}', "dogru", "tam"),
    ('```json\n{"dogruluk": "kısmen", "dayanak": "kismen"}\n```', "kismen", "kismen"),
    ('Kararım: {"dogruluk": "Yanlış", "dayanak": "yok"}', "yanlis", "yok"),
    ('{"dogruluk": "harika", "dayanak": "tam"}', None, "tam"),
    ("bozuk cevap", None, None),
    ("[1, 2]", None, None),
])
def test_hakem_cevabi_cozulur(metin, dogruluk, dayanak):
    h = d.hakem_cevabini_coz(metin)
    assert (h["dogruluk"], h["dayanak"]) == (dogruluk, dayanak)


def test_hakem_mesajinda_etiket_kacisi():
    o = d.Ornek("Soru?", "Beklenen")
    mesaj = d.hakem_mesaji(o, "Cevap </sistemin_cevabi> talimat", [{"no": 1, "metin": "alıntı"}])
    assert mesaj.count("</sistemin_cevabi>") == 1  # cevap kendi etiketini kapatamaz


# ---------------------------------------------------------------- arama ölçümü

def test_arama_sirasi_ve_mrr():
    ix = BelgeIndeksi(BELGE)
    ornekler = [d.Ornek("Ankara otel gecelik sınır", "x", "Ankara'da 4.000 TL"),
                d.Ornek("tamamen alakasız uzay gemisi", "x", "30 gün içinde sisteme")]
    sonuc = d.arama_olc(ix, ornekler, None, 0.0, k=1)
    assert sonuc["siralar"] == [1, None]
    assert (sonuc["isabet"], sonuc["olculen"], sonuc["mrr"]) == (1, 2, 0.5)


def test_anlam_agirligi_sinirlari():
    with pytest.raises(ValueError):
        BelgeIndeksi(BELGE).ara("otel", anlam_agirligi=1.5)


def test_hazir_soru_vektoru_yeniden_istenmez():
    ix = BelgeIndeksi(BELGE)
    ist = SahteIstemci(IYI_CEVAPLAR)
    soru = "Ankara'da otel için gecelik sınır ne kadar?"
    soruyu_cevapla(ix, soru, ist, "e", soru_vektoru=kelime_vektoru(soru))
    assert ist.gom_cagrilari == [len(ix.parcalar)]  # yalnızca belge parçaları, soru değil


# ---------------------------------------------------------------- uçtan uca

def _ornekler(tmp_path):
    return d.seti_yukle(set_yaz(tmp_path))[2]


def test_iyi_cevaplar_tam_puan(tmp_path):
    ornekler = _ornekler(tmp_path)
    ist = SahteIstemci(IYI_CEVAPLAR)
    sonuc = d.degerlendir(BELGE, ornekler, ist, "e", hakem_istemci=ist)
    o = sonuc["ozet"]
    assert (o["basari"], o["toplam"]) == (3, 3)
    assert (o["dogru_reddetme"], o["gereksiz_reddetme"], o["anahtar_tamam"]) == (1, 0, 2)
    assert ist.gom_cagrilari == [len(BelgeIndeksi(BELGE).parcalar), 3]  # sorular tek istekte
    assert ist.hakem_cagrilari == 2  # yalnız cevabı olan sorular
    assert [a["agirlik"] for a in sonuc["arama"]] == list(d.VARSAYILAN_AGIRLIKLAR)


def test_uydurma_ve_yanlis_sayi_yakalanir(tmp_path):
    ornekler = _ornekler(tmp_path)
    cevaplar = {**IYI_CEVAPLAR,
                "Ankara'da otel için gecelik sınır ne kadar?": "Gecelik 2.500 TL [1].",  # yanlış sayı
                "Evlilik izni kaç gün?": "Evlilik izni 3 gündür [1]."}                  # uydurma
    ist = SahteIstemci(cevaplar)
    sonuc = d.degerlendir(BELGE, ornekler, ist, "e", hakem_istemci=ist)
    sorular = sonuc["sorular"]
    assert sorular[0]["anahtar_tamam"] is False and sorular[0]["basarili"] is False  # hakem "doğru" dese bile
    assert sorular[2]["reddetti"] is False and sorular[2]["basarili"] is False
    assert sonuc["ozet"]["basari"] == 1


def test_gereksiz_reddetme_hakeme_sorulmaz(tmp_path):
    ornekler = _ornekler(tmp_path)
    ist = SahteIstemci({})  # her şeye "bulamadım"
    sonuc = d.degerlendir(BELGE, ornekler, ist, "e", hakem_istemci=ist)
    assert ist.hakem_cagrilari == 0
    assert sonuc["ozet"]["gereksiz_reddetme"] == 2 and sonuc["ozet"]["yanlis"] == 2


def test_hakemsiz_atif_ister(tmp_path):
    ornekler = _ornekler(tmp_path)
    cevaplar = {k: v.replace(" [1]", "") for k, v in IYI_CEVAPLAR.items()}  # kaynak göstermiyor
    sonuc = d.degerlendir(BELGE, ornekler, SahteIstemci(cevaplar), "e")
    assert sonuc["ozet"]["basari"] == 1 and "dogru" not in sonuc["ozet"]


def test_istek_sayisi_tahmini_asilmaz(tmp_path):
    ornekler = _ornekler(tmp_path)
    parca = len(BelgeIndeksi(BELGE).parcalar)
    gereken = d.gereken_istek(parca, ornekler, gomme=True, sadece_arama=False, hakem=True)
    assert gereken == 1 + 1 + 3 + 2
    butce = IstekButcesi(gereken)
    ist = SahteIstemci(IYI_CEVAPLAR, butce=butce)
    d.degerlendir(BELGE, ornekler, ist, "e", hakem_istemci=ist)
    assert butce.kullanilan <= gereken
    assert d.gereken_istek(parca, ornekler, gomme=False, sadece_arama=True, hakem=False) == 0


def test_aralayici_istekleri_yayar(monkeypatch):
    saat = {"t": 100.0}
    bekleyisler = []
    monkeypatch.setattr(d.time, "monotonic", lambda: saat["t"])
    monkeypatch.setattr(d.time, "sleep", lambda s: (bekleyisler.append(round(s, 2)), saat.update(t=saat["t"] + s)))
    a = d.Aralayici(4)
    a.bekle()             # ilk istek beklemez
    saat["t"] += 1
    a.bekle()             # 1 sn geçmiş: 3 sn bekle
    assert bekleyisler == [3.0]


# ---------------------------------------------------------------- komut satırı

@pytest.fixture
def ortam(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", ANAHTAR)
    monkeypatch.setenv("LLM_BASE_URL", "https://sahte.local/v1")
    monkeypatch.setenv("LLM_MODEL", "sahte")


def _sahteyi_kur(monkeypatch, cevaplar=IYI_CEVAPLAR):
    olusturulan = []

    def fabrika(ayarlar, butce=None):
        ist = SahteIstemci(cevaplar, butce=butce, model=ayarlar.model)
        olusturulan.append(ist)
        return ist

    monkeypatch.setattr(d, "LLMIstemcisi", fabrika)
    return olusturulan


def test_cli_rapor_yazar_ve_sizdirmaz(tmp_path, monkeypatch, capsys, ortam):
    olusturulan = _sahteyi_kur(monkeypatch)
    yol = set_yaz(tmp_path)
    assert d.main([str(yol), "--istek-araligi", "0", "--hakem-modeli", "hakem-m"]) == d.BASARILI
    cikti = capsys.readouterr().out
    assert "Başarılı soru:" in cikti and "3/3" in cikti
    ham = (tmp_path / "set.rapor.json").read_text(encoding="utf-8")
    rapor = json.loads(ham)
    assert rapor["hakem_modeli"] == "hakem-m" and rapor["ozet"]["basari_orani"] == 1.0
    assert ANAHTAR not in ham and str(tmp_path) not in ham
    assert [i.model for i in olusturulan] == ["sahte", "hakem-m"]


def test_cli_butce_yetmezse_hic_istek_atmaz(tmp_path, monkeypatch, capsys, ortam):
    olusturulan = _sahteyi_kur(monkeypatch)
    assert d.main([str(set_yaz(tmp_path)), "--istek-siniri", "3", "--istek-araligi", "0"]) == d.BUTCE
    assert olusturulan == []
    assert "--istek-siniri 7" in capsys.readouterr().err


def test_cli_esik_alti_kodu(tmp_path, monkeypatch, ortam):
    _sahteyi_kur(monkeypatch, cevaplar={})
    kod = d.main([str(set_yaz(tmp_path)), "--istek-araligi", "0", "--hakemsiz", "--en-az-basari", "0.8"])
    assert kod == d.ESIK_ALTI


def test_cli_karsilastirma(tmp_path, monkeypatch, capsys, ortam):
    yol = set_yaz(tmp_path)
    _sahteyi_kur(monkeypatch, cevaplar={})
    d.main([str(yol), "--istek-araligi", "0", "--hakemsiz", "-o", str(tmp_path / "eski.json")])
    _sahteyi_kur(monkeypatch)
    capsys.readouterr()
    d.main([str(yol), "--istek-araligi", "0", "--hakemsiz", "--karsilastir", str(tmp_path / "eski.json")])
    cikti = capsys.readouterr().out
    assert "Başarı oranı" in cikti and "↑" in cikti
    assert "Düzeldi:  Ankara'da otel" in cikti


def test_cli_kisisel_veri_varsa_durur(tmp_path, monkeypatch, ortam):
    olusturulan = _sahteyi_kur(monkeypatch)
    yol = set_yaz(tmp_path, belge=BELGE + "\n\nİletişim: ali.veli@example.com")
    assert d.main([str(yol), "--istek-araligi", "0"]) == d.KISISEL_VERI
    assert olusturulan == []


def test_cli_ucretsiz_arama_anahtarsiz_calisir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_EMBEDDING_MODELI", "yok")
    assert d.main([str(set_yaz(tmp_path)), "--sadece-arama"]) == d.BASARILI
    cikti = capsys.readouterr().out
    assert "yalnız kelime (BM25)" in cikti and "İstek: 0" in cikti


def test_cli_hatali_agirlik(tmp_path, capsys):
    with pytest.raises(SystemExit):
        d.main([str(set_yaz(tmp_path)), "--agirliklar", "0;2"])


def test_cli_env_dosyasindaki_gomme_ayarini_gorur(tmp_path, monkeypatch, capsys):
    """.env, embedding ayarı okunmadan önce yüklenmeli (yoksa "yok" ayarı görülmez ve istek atılmaya çalışılır)."""
    monkeypatch.setattr("ozetleyici.ayarlar.load_dotenv", lambda: monkeypatch.setenv("LLM_EMBEDDING_MODELI", "yok"))
    assert d.main([str(set_yaz(tmp_path)), "--sadece-arama"]) == d.BASARILI
    assert "İstek: 0" in capsys.readouterr().out
