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
    def __init__(self, ayarlar):
        self.model = ayarlar.model
        self.ocr_girdi_token = 0
        self.ocr_cikti_token = 0
        self.gorseller = []

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
        for p in ("Uzaktan ", "çalışma ", "özeti"):
            parca_gelince(p)
        return LLMCevabi("Uzaktan çalışma özeti", 40, 6, 1, model=self.model)

    def gorseli_metne_cevir(self, png):
        self.gorseller.append(png)
        self.ocr_girdi_token += 100
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
    def fabrika(a):
        olusan.append(SahteIstemci(a)); return olusan[-1]
    o = olaylar(gonder(istemci(fabrika=fabrika), tampon.getvalue(), ad="fis.png", ocr="gemini"))
    assert o[-1]["tip"] == "bitti"
    assert o[-1]["sonuc"]["saglayiciya_gonderilen_gorsel"] == 1 and o[-1]["sonuc"]["ocr_girdi_token"] == 100
    assert len(olusan) == 1 and len(olusan[0].gorseller) == 1  # tek istemci, OCR + özet


def test_okuma_hatasi_olay_olarak_doner():
    o = olaylar(gonder(istemci(), b"MZ", ad="virus.exe"))
    assert o[-1]["tip"] == "hata" and "Desteklenmeyen" in o[-1]["mesaj"]


# ------------------------------------------------------------------ gizlilik

def test_kisisel_veri_varsa_saglayiciya_gitmeden_sorar():
    olusan = []
    o = olaylar(gonder(istemci(fabrika=lambda a: olusan.append(1) or SahteIstemci(a)),
                       "Müşteri: ayse@example.com".encode()))
    assert o[-1] == {"tip": "kisisel_veri", "bulgular": {"e-posta": 1}}
    assert olusan == []  # istemci hiç oluşturulmadı: sağlayıcıya istek gitmedi
    assert "ayse@" not in json.dumps(o, ensure_ascii=False)


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
    assert acilan == [] and o[-1]["tip"] in ("bitti", "hata")
