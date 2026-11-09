"""Web uygulamasının testleri: işlev ve her güvenlik önlemi ayrı ayrı."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from ozetleyici.ayarlar import AyarHatasi, Ayarlar
from ozetleyici.llm import LLMCevabi, LLMHatasi
from ozetleyici.web.uygulama import EN_BUYUK_YUKLEME, uygulama_olustur

ANAHTAR = "web-test-anahtari-0001"
OTURUM = "test-oturum-anahtari"
AYAR = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="sahte-model")


class SahteIstemci:
    def __init__(self, ayarlar, butce=None):
        self.model = ayarlar.model
        self.butce = butce
        self.okuma_girdi_token = 0
        self.okuma_cikti_token = 0
        self.gorseller = []

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
        if self.butce:
            self.butce.harca()
        for p in ("Uzaktan ", "çalışma ", "özeti"):
            if parca_gelince:
                parca_gelince(p)
        return LLMCevabi("Uzaktan çalışma özeti", 40, 6, 1, model=self.model)

    def modelleri_listele(self):
        return ["sahte-model", "gemini-buyuk-pro", "gemini-hizli-flash", "gemini-embedding-001"]

    def gom(self, metinler, model):
        if self.butce:
            self.butce.harca()
        from tests.test_soru import kelime_vektoru
        return [kelime_vektoru(m) for m in metinler]

    def gorseli_metne_cevir(self, png):
        self.gorseller.append(png)
        self.okuma_girdi_token += 100
        return "Görüntüden okunan metin"


def istemci(ayar_yukleyici=lambda: AYAR, fabrika=SahteIstemci):
    app = uygulama_olustur(ayar_yukleyici=ayar_yukleyici, istemci_fabrikasi=fabrika, oturum_anahtari=OTURUM)
    return TestClient(app, base_url="http://127.0.0.1:8765")


def gonder(c, veri: bytes, ad="belge.txt", oturum=OTURUM, **parametre):
    basliklar = {"X-Oturum-Anahtari": oturum, "Content-Type": "application/octet-stream"} if oturum else {}
    return c.post("/api/ozetle", params={"ad": ad, **parametre}, content=veri, headers=basliklar)


def olaylar(cevap):
    return [json.loads(s) for s in cevap.text.splitlines() if s.strip()]


# ------------------------------------------------------------------ işlev

def test_ana_sayfa_oturum_anahtarini_icerir():
    c = istemci()
    cevap = c.get("/")
    assert cevap.status_code == 200
    assert f'<meta name="oturum" content="{OTURUM}">' in cevap.text
    assert c.get("/statik/uygulama.js").status_code == 200


def test_durum():
    d = istemci().get("/api/durum", headers={"X-Oturum-Anahtari": OTURUM}).json()
    assert d["model"] == "sahte-model" and d["ayar_hatasi"] is None
    assert ".docx" in d["desteklenen"] and ".xlsx" in d["desteklenen"]


def test_durum_ayar_hatasini_bildirir():
    def bozuk():
        raise AyarHatasi("LLM_API_KEY eksik")
    d = istemci(ayar_yukleyici=bozuk).get("/api/durum", headers={"X-Oturum-Anahtari": OTURUM}).json()
    assert d["model"] is None and "LLM_API_KEY" in d["ayar_hatasi"]


def test_ozet_akis_halinde_gelir():
    cevap = gonder(istemci(), "Şirket haftada üç gün uzaktan çalışmaya izin verir.".encode(), uzunluk="kisa")
    assert cevap.status_code == 200 and cevap.headers["content-type"].startswith("application/x-ndjson")
    o = olaylar(cevap)
    assert [x["metin"] for x in o if x["tip"] == "parca"] == ["Uzaktan ", "çalışma ", "özeti"]
    bitti = o[-1]
    assert bitti["tip"] == "bitti" and bitti["sonuc"]["ozet"] == "Uzaktan çalışma özeti"
    assert bitti["sonuc"]["kaynak_dosya"] == "belge.txt" and bitti["sonuc"]["belge_turu"] == "metin"


def test_word_dosyasi_ozetlenir():
    from docx import Document
    d = Document(); d.add_paragraph("Toplantı kararları: bütçe onaylandı.")
    tampon = io.BytesIO(); d.save(tampon)
    o = olaylar(gonder(istemci(), tampon.getvalue(), ad="karar.docx"))
    assert o[-1]["tip"] == "bitti" and o[-1]["sonuc"]["belge_turu"] == "word"


def test_gemini_ocr_gorseli_saglayiciya_gonderir():
    from PIL import Image
    tampon = io.BytesIO(); Image.new("RGB", (300, 100), "white").save(tampon, format="PNG")
    olusan = []
    def fabrika(a, **k):
        olusan.append(SahteIstemci(a, **k)); return olusan[-1]
    o = olaylar(gonder(istemci(fabrika=fabrika), tampon.getvalue(), ad="fis.png", ocr="gemini"))
    assert o[-1]["tip"] == "bitti"
    assert o[-1]["sonuc"]["saglayiciya_gonderilen_gorsel"] == 1 and o[-1]["sonuc"]["okuma_girdi_token"] == 100
    assert len(olusan) == 1 and len(olusan[0].gorseller) == 1  # tek istemci, OCR + özet


def test_okuma_hatasi_olay_olarak_doner():
    o = olaylar(gonder(istemci(), b"MZ", ad="virus.exe"))
    assert o[-1]["tip"] == "hata" and "Desteklenmeyen" in o[-1]["mesaj"]


# ------------------------------------------------------------------ gizlilik

def test_kisisel_veri_varsa_saglayiciya_gitmeden_sorar():
    olusan = []
    o = olaylar(gonder(istemci(fabrika=lambda a, **k: olusan.append(1) or SahteIstemci(a, **k)),
                       "Müşteri: ayse@example.com".encode()))
    assert o[-1] == {"tip": "kisisel_veri", "bulgular": {"e-posta": 1}}
    assert olusan == []  # istemci hiç oluşturulmadı: sağlayıcıya istek gitmedi
    # Uyarının kendisi değeri içermez (yalnızca tür ve adet). Okunan metin "kaynak" olayıyla
    # yalnızca bu bilgisayardaki tarayıcıya gider; kullanıcı neyin bulunduğunu görebilsin diye.
    assert "ayse@" not in json.dumps(o[-1], ensure_ascii=False)


def test_kullanici_onaylarsa_gonderilir():
    o = olaylar(gonder(istemci(), "Müşteri: ayse@example.com".encode(), yine_de_gonder="1"))
    assert o[-1]["tip"] == "bitti"


def test_hata_mesajinda_anahtar_gizlenir():
    class Sizdiran(SahteIstemci):
        def tamamla(self, *a, **k):
            from ozetleyici.ayarlar import anahtari_gizle
            raise LLMHatasi(anahtari_gizle(f"sunucu cevabı: {ANAHTAR}", ANAHTAR))
    cevap = gonder(istemci(fabrika=Sizdiran), b"metin")
    assert ANAHTAR not in cevap.text and "web-***" in cevap.text


def test_beklenmeyen_hata_ayrinti_sizdirmaz():
    class Patlayan(SahteIstemci):
        def tamamla(self, *a, **k):
            raise RuntimeError(f"iç ayrıntı {ANAHTAR} /home/kullanici/gizli")
    o = olaylar(gonder(istemci(fabrika=Patlayan), b"metin"))
    assert o[-1] == {"tip": "hata", "mesaj": "Beklenmeyen bir hata oluştu. Ayrıntı terminalde."}


# ------------------------------------------------------------------ güvenlik

def test_oturum_anahtari_olmadan_api_reddedilir():
    c = istemci()
    assert gonder(c, b"metin", oturum=None).status_code == 403
    assert gonder(c, b"metin", oturum="yanlis").status_code == 403
    assert c.get("/api/durum").status_code == 403


def test_yabanci_host_reddedilir_dns_rebinding():
    c = istemci()
    cevap = c.get("/", headers={"Host": "kotu-site.com"})
    assert cevap.status_code == 400


def test_cors_izni_yok():
    cevap = istemci().options("/api/ozetle", headers={
        "Origin": "https://kotu-site.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-oturum-anahtari"})
    assert "access-control-allow-origin" not in {k.lower() for k in cevap.headers}


def test_guvenlik_basliklari():
    b = istemci().get("/").headers
    assert "script-src 'self'" in b["content-security-policy"] and "frame-ancestors 'none'" in b["content-security-policy"]
    assert b["x-content-type-options"] == "nosniff" and b["x-frame-options"] == "DENY"
    assert b["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in b} or "uvicorn" not in b.get("server", "")


def test_api_belgeleri_kapali():
    c = istemci()
    for yol in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(yol).status_code == 404


def test_buyuk_dosya_reddedilir():
    cevap = gonder(istemci(), b"x" * (EN_BUYUK_YUKLEME + 1))
    assert cevap.status_code == 413 and "çok büyük" in cevap.json()["hata"]


def test_dosya_adindaki_yol_atilir():
    o = olaylar(gonder(istemci(), b"metin", ad="../../Windows/system32/belge.txt"))
    assert o[-1]["sonuc"]["kaynak_dosya"] == "belge.txt"


def test_gecersiz_parametreler():
    c = istemci()
    assert gonder(c, b"m", uzunluk="dev").status_code == 400
    assert gonder(c, b"m", ocr="hepsi").status_code == 400
    assert gonder(c, b"").status_code == 400


def test_ayni_anda_tek_is():
    import threading
    bekle, devam = threading.Event(), threading.Event()

    class Yavas(SahteIstemci):
        def tamamla(self, *a, **k):
            bekle.set(); devam.wait(5)
            return super().tamamla(*a, **k)

    c = istemci(fabrika=Yavas)
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.setdefault("ilk", gonder(c, b"birinci")))
    t.start(); assert bekle.wait(5)
    ikinci = gonder(c, b"ikinci")
    devam.set(); t.join(5)
    assert ikinci.status_code == 429
    assert olaylar(sonuc["ilk"])[-1]["tip"] == "bitti"
    assert gonder(c, b"ucuncu").status_code == 200  # kilit bırakıldı


def test_yuklenen_dosya_diske_yazilmaz(tmp_path, monkeypatch):
    import tempfile
    acilan = []
    gercek = tempfile.SpooledTemporaryFile
    monkeypatch.setattr(tempfile, "SpooledTemporaryFile", lambda *a, **k: acilan.append(1) or gercek(*a, **k))
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda *a, **k: acilan.append(1) or (_ for _ in ()).throw(AssertionError("diske yazma")))
    o = olaylar(gonder(istemci(), b"x " * (2 * 1024 * 1024)))  # 4 MB: multipart olsaydı diske taşardı
    assert acilan == [] and o[-1]["tip"] in ("bitti", "hata", "onay_gerekli")



# ------------------------------------------------------------------ bütçe ve iptal

UZUN = "\n\n".join(["Uzun bir paragraf. " * 300] * 30).encode()  # ~16 istek


def test_butce_asilinca_onay_istenir_ve_istek_gitmez():
    olusan = []
    ayar = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="m", istek_siniri=5)
    o = olaylar(gonder(istemci(ayar_yukleyici=lambda: ayar,
                               fabrika=lambda a, **k: olusan.append(1) or SahteIstemci(a, **k)), UZUN))
    assert o[-1]["tip"] == "onay_gerekli" and o[-1]["sinir"] == 5 and o[-1]["gereken"] > 5
    assert olusan == []


def test_onaydan_sonra_yukseltilmis_sinirla_devam():
    ayar = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="m", istek_siniri=5)
    c = istemci(ayar_yukleyici=lambda: ayar)
    gereken = olaylar(gonder(c, UZUN))[-1]["gereken"]
    o = olaylar(gonder(c, UZUN, istek_siniri=str(gereken)))
    assert o[-1]["tip"] == "bitti" and o[-1]["sonuc"]["kullanilan_istek"] == gereken


def test_gecersiz_istek_siniri():
    assert gonder(istemci(), b"m", istek_siniri="0").status_code == 400
    assert gonder(istemci(), b"m", istek_siniri="5000").status_code == 400


def test_sekme_kapaninca_is_durur():
    """Gerçek sunucu + gerçek bağlantı kopması: kalan istekler gönderilmemeli."""
    import socket
    import threading
    import time

    import httpx
    import uvicorn

    istekler = []
    ilk_parca = threading.Event()

    class Yavas(SahteIstemci):
        def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
            if self.butce:
                self.butce.harca()
            istekler.append(1)
            if parca_gelince:
                parca_gelince("ilk ")
            ilk_parca.set()
            time.sleep(0.3)
            return LLMCevabi("not", 1, 1, 1, model=self.model)

    ayar = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="m", istek_siniri=100)
    app = uygulama_olustur(lambda: ayar, Yavas, oturum_anahtari=OTURUM)
    with socket.socket() as s_:
        s_.bind(("127.0.0.1", 0)); port = s_.getsockname()[1]
    sunucu = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=sunucu.run, daemon=True); t.start()
    while not sunucu.started:
        time.sleep(0.05)
    try:
        with httpx.Client(timeout=10) as c:
            with c.stream("POST", f"http://127.0.0.1:{port}/api/ozetle", params={"ad": "uzun.txt"}, content=UZUN,
                          headers={"X-Oturum-Anahtari": OTURUM}) as cevap:
                assert cevap.status_code == 200
                assert ilk_parca.wait(5)
            # bağlantı burada kapandı (sekme kapatıldı)
            kapanista = len(istekler)
        # İş, istek sayısı artmayı bırakana kadar beklenir. İşletim sistemi bağlantı kopmasını
        # biraz geç fark edebilir (Windows'ta 1-3 istek); önemli olan işin sonunda durması.
        son, sabit_basladi = len(istekler), time.monotonic()
        bitis = time.monotonic() + 15
        while time.monotonic() < bitis and time.monotonic() - sabit_basladi < 1.5:
            time.sleep(0.1)
            if len(istekler) != son:
                son, sabit_basladi = len(istekler), time.monotonic()
        assert time.monotonic() - sabit_basladi >= 1.5, "istekler durmadı"
        assert son < 16, f"belgenin tamamı işlendi ({son} istek); iptal çalışmadı"
        assert son - kapanista <= 6, f"kapanıştan sonra çok fazla istek gitti ({son - kapanista})"
    finally:
        sunucu.should_exit = True
        t.join(5)


# ------------------------------------------------------------------ ses ve video

def test_video_yuklenir_yerel_yaziya_dokulur():
    from tests.medya_uret import video_dosyasi
    app = uygulama_olustur(lambda: AYAR, SahteIstemci, oturum_anahtari=OTURUM,
                           transkriptor=lambda pcm, model: "[00:00] Proje teslim tarihi ertelendi.")
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    o = olaylar(gonder(c, video_dosyasi("mp4", "mpeg4", "aac", saniye=2), ad="toplanti.mp4"))
    assert o[-1]["tip"] == "bitti"
    s = o[-1]["sonuc"]
    assert s["belge_turu"] == "video" and s["ses_suresi_sn"] >= 1.8 and s["saglayiciya_gonderilen_ses_parcasi"] == 0
    assert any("görüntüdeki yazı" in x["mesaj"] for x in o if x["tip"] == "not")


def test_medya_icin_daha_buyuk_sinir_belge_icin_degil():
    from ozetleyici.web.uygulama import EN_BUYUK_MEDYA
    c = istemci()
    orta = b"x" * (EN_BUYUK_YUKLEME + 10)
    assert gonder(c, orta, ad="belge.txt").status_code == 413
    assert gonder(c, orta, ad="kayit.mp3").status_code == 200  # boyut uygun; içerik sonra denetlenir
    assert gonder(c, b"x" * (EN_BUYUK_MEDYA + 1), ad="kayit.mp3").status_code == 413


def test_gecersiz_ses_secenegi():
    assert gonder(istemci(), b"m", ses="bulut").status_code == 400


def test_durum_medya_bilgisi():
    d = istemci().get("/api/durum", headers={"X-Oturum-Anahtari": OTURUM}).json()
    assert ".mp4" in d["medya"] and ".mp3" in d["desteklenen"]
    assert d["whisper"]["model"] == "small" and d["istek_siniri"] == 20



# ------------------------------------------------------------------ model seçimi

def test_model_listesi_filtrelenmis_ve_varsayilan_basta():
    d = istemci().get("/api/modeller", headers={"X-Oturum-Anahtari": OTURUM}).json()
    assert d["modeller"] == ["sahte-model", "gemini-hizli-flash", "gemini-buyuk-pro"]
    assert d["varsayilan"] == "sahte-model" and d["hata"] is None


def test_model_listesi_oturum_anahtari_ister():
    assert istemci().get("/api/modeller").status_code == 403


def test_secilen_model_kullanilir():
    kullanilan = []

    class Kaydeden(SahteIstemci):
        def tamamla(self, *a, **k):
            kullanilan.append(self.model)
            return super().tamamla(*a, **k)

    o = olaylar(gonder(istemci(fabrika=Kaydeden), b"metin", model="gemini-buyuk-pro"))
    assert o[-1]["tip"] == "bitti" and kullanilan == ["gemini-buyuk-pro"]
    assert o[-1]["sonuc"]["model"] == "gemini-buyuk-pro"


def test_listede_olmayan_model_reddedilir():
    c = istemci()
    assert gonder(c, b"metin", model="gemini-embedding-001").status_code == 400  # filtrelenmiş
    assert gonder(c, b"metin", model="kotu/model").status_code == 400


def test_baska_modelde_maliyet_gosterilmez():
    ayar = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="sahte-model",
                   girdi_fiyati=0.3, cikti_fiyati=2.5)
    c = istemci(ayar_yukleyici=lambda: ayar)
    varsayilan = olaylar(gonder(c, b"metin"))[-1]["sonuc"]
    baska = olaylar(gonder(c, b"metin", model="gemini-hizli-flash"))
    assert varsayilan["maliyet_usd"] is not None
    assert baska[-1]["sonuc"]["maliyet_usd"] is None
    assert any("maliyet hesaplanmadı" in x["mesaj"] for x in baska if x["tip"] == "not")


def test_model_listesi_alinamazsa_yalnizca_varsayilan():
    class Bozuk(SahteIstemci):
        def modelleri_listele(self):
            raise LLMHatasi("Model listesi alınamadı (APIConnectionError).")

    d = istemci(fabrika=Bozuk).get("/api/modeller", headers={"X-Oturum-Anahtari": OTURUM}).json()
    assert d["modeller"] == ["sahte-model"] and "alınamadı" in d["hata"]


def test_model_listesi_onbellekte_tutulur():
    sayac = []

    class Sayan(SahteIstemci):
        def modelleri_listele(self):
            sayac.append(1)
            return super().modelleri_listele()

    c = istemci(fabrika=Sayan)
    for _ in range(3):
        c.get("/api/modeller", headers={"X-Oturum-Anahtari": OTURUM})
    gonder(c, b"metin", model="gemini-buyuk-pro")
    assert sayac == [1]  # sağlayıcıya bir kez soruldu


# ------------------------------------------------------------------ arayüz olayları

def test_asamalar_ve_kaynak_metin_gonderilir():
    o = olaylar(gonder(istemci(), "Şirket bütçeyi onayladı.".encode()))
    tipler = [x["tip"] for x in o]
    assert tipler.index("asama") < tipler.index("kaynak") < tipler.index("parca")
    assert [x["ad"] for x in o if x["tip"] == "asama"] == ["okuma", "ozet"]
    kaynak = next(x for x in o if x["tip"] == "kaynak")
    assert kaynak["metin"] == "Şirket bütçeyi onayladı." and kaynak["kesildi"] is False
    assert o[-1]["sonuc"]["saglayiciya_giden_karakter"] == len("Şirket bütçeyi onayladı.")


def test_kisisel_veride_kaynak_gosterilir_ama_disari_gitmez():
    o = olaylar(gonder(istemci(), "Müşteri: ayse@example.com".encode()))
    assert any(x["tip"] == "kaynak" for x in o) and o[-1]["tip"] == "kisisel_veri"


def test_odak_modele_iletilir():
    sistemler = []

    class Kaydeden(SahteIstemci):
        def tamamla(self, sistem, *a, **k):
            sistemler.append(sistem)
            return super().tamamla(sistem, *a, **k)

    o = olaylar(gonder(istemci(fabrika=Kaydeden), b"metin", odak="teslim tarihleri"))
    assert "<odak>teslim tarihleri</odak>" in sistemler[0] and o[-1]["sonuc"]["odak"] == "teslim tarihleri"


def test_cok_uzun_odak_reddedilir():
    assert gonder(istemci(), b"m", odak="x" * 301).status_code == 400



# ------------------------------------------------------------------ belgeye soru sorma

POLITIKA = ("Uzaktan çalışma politikası.\n\nKaybolan veya çalınan cihaz 24 saat içinde bilgi güvenliği "
            "ekibine bildirilir.\n\nŞirket aylık 400 TL internet desteği verir.").encode()


def ozetle_ve_kimlik(c, veri=POLITIKA):
    o = olaylar(gonder(c, veri))
    assert o[-1]["tip"] == "bitti" and o[-1]["belge_id"]
    return o[-1]["belge_id"]


def sor(c, govde, oturum=OTURUM):
    return c.post("/api/sor", json=govde, headers={"X-Oturum-Anahtari": oturum} if oturum else {})


class CevaplayanIstemci(SahteIstemci):
    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
        if self.butce:
            self.butce.harca()
        metin = "Cihaz 24 saat içinde bildirilir [1]." if "<alinti" in kullanici else "Özet."
        if parca_gelince:
            parca_gelince(metin)
        return LLMCevabi(metin, 30, 8, 1, model=self.model)


def test_ozetten_sonra_soru_sorulur_ve_kaynak_doner():
    c = istemci(fabrika=CevaplayanIstemci)
    kimlik = ozetle_ve_kimlik(c)
    o = olaylar(sor(c, {"belge_id": kimlik, "soru": "Kaybolan cihaz ne zaman bildirilir?"}))
    assert [x["metin"] for x in o if x["tip"] == "parca"] == ["Cihaz 24 saat içinde bildirilir [1]."]
    s = o[-1]["sonuc"]
    assert o[-1]["tip"] == "bitti" and s["anlamsal"] is True
    assert s["kaynaklar"][0]["kullanildi"] and "24 saat" in s["kaynaklar"][0]["metin"]
    kaynak = s["kaynaklar"][0]
    assert POLITIKA.decode()[kaynak["baslangic"]:].startswith(kaynak["metin"][:15])


def test_bilinmeyen_belge_404():
    assert sor(istemci(), {"belge_id": "yok", "soru": "soru"}).status_code == 404


def test_soru_oturum_anahtari_ister():
    assert sor(istemci(), {"belge_id": "x", "soru": "soru"}, oturum=None).status_code == 403


@pytest.mark.parametrize("govde,kod", [
    ({"belge_id": "x", "soru": ""}, 400),
    ({"belge_id": "x", "soru": "x" * 501}, 400),
    ({"belge_id": "x", "soru": "a", "istek_siniri": 0}, 400),
    ({"belge_id": "x", "soru": "a", "istek_siniri": "çok"}, 400),
    ([1, 2], 400),
])
def test_gecersiz_soru_istekleri(govde, kod):
    assert sor(istemci(), govde).status_code == kod


def test_cok_buyuk_istek_reddedilir():
    c = istemci()
    cevap = c.post("/api/sor", content=b"{" + b" " * 9000 + b"}", headers={"X-Oturum-Anahtari": OTURUM})
    assert cevap.status_code == 413


def test_kisisel_veride_durulan_belgeye_soru_sorulamaz():
    o = olaylar(gonder(istemci(), "Müşteri: ayse@example.com".encode()))
    assert o[-1]["tip"] == "kisisel_veri" and "belge_id" not in o[-1]


def test_soru_butcesi_asilinca_onay_istenir():
    ayar = Ayarlar(api_anahtari=ANAHTAR, base_url="https://sahte.local/v1", model="m", istek_siniri=2)
    c = istemci(ayar_yukleyici=lambda: ayar, fabrika=CevaplayanIstemci)
    kimlik = ozetle_ve_kimlik(c)
    o = olaylar(sor(c, {"belge_id": kimlik, "soru": "cihaz"}))
    assert o[-1]["tip"] == "onay_gerekli" and o[-1]["gereken"] == 3  # 1 gömme + 1 soru vektörü + 1 cevap
    o = olaylar(sor(c, {"belge_id": kimlik, "soru": "cihaz", "istek_siniri": 3}))
    assert o[-1]["tip"] == "bitti" and o[-1]["sonuc"]["kullanilan_istek"] == 3


def test_ikinci_soruda_belge_yeniden_gomulmez():
    c = istemci(fabrika=CevaplayanIstemci)
    kimlik = ozetle_ve_kimlik(c)
    olaylar(sor(c, {"belge_id": kimlik, "soru": "cihaz"}))
    o = olaylar(sor(c, {"belge_id": kimlik, "soru": "internet desteği"}))
    assert o[-1]["sonuc"]["kullanilan_istek"] == 2  # soru vektörü + cevap


def test_embedding_yoksa_kelime_aramasiyla_cevaplar():
    from ozetleyici.llm import GommeKullanilamiyor

    class GommesizIstemci(CevaplayanIstemci):
        def gom(self, metinler, model):
            raise GommeKullanilamiyor("bu sağlayıcıda embedding yok")

    c = istemci(fabrika=GommesizIstemci)
    kimlik = ozetle_ve_kimlik(c)
    o = olaylar(sor(c, {"belge_id": kimlik, "soru": "Kaybolan cihaz?"}))
    assert o[-1]["tip"] == "bitti" and o[-1]["sonuc"]["anlamsal"] is False
    assert any("kelime eşleşmesiyle" in x["mesaj"] for x in o if x["tip"] == "not")


def test_belge_deposu_sinirlari():
    from ozetleyici.web.uygulama import BelgeDeposu
    depo = BelgeDeposu(en_fazla=2, omur_sn=3600)
    a, b, c_ = depo.ekle("a", "metin a"), depo.ekle("b", "metin b"), depo.ekle("c", "metin c")
    assert depo.al(a) is None and depo.al(b) and depo.al(c_)  # en eskisi silindi
    eski = BelgeDeposu(omur_sn=-1)
    kimlik = eski.ekle("x", "metin")
    assert eski.al(kimlik) is None  # süresi doldu
    assert len(a) >= 20  # tahmin edilemez kimlik


def test_soru_ve_ozet_ayni_anda_calismaz():
    import threading
    bekle, devam = threading.Event(), threading.Event()

    class Yavas(CevaplayanIstemci):
        def tamamla(self, sistem, kullanici, *a, **k):
            if "<alinti" in kullanici:
                bekle.set(); devam.wait(5)
            return super().tamamla(sistem, kullanici, *a, **k)

    c = istemci(fabrika=Yavas)
    kimlik = ozetle_ve_kimlik(c)
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.setdefault("s", sor(c, {"belge_id": kimlik, "soru": "cihaz"})))
    t.start(); assert bekle.wait(5)
    assert gonder(c, b"ikinci belge").status_code == 429
    devam.set(); t.join(5)
    assert olaylar(sonuc["s"])[-1]["tip"] == "bitti"
