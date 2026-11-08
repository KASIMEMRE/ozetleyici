import json

import pytest

from ozetleyici import __main__ as cli
from ozetleyici.llm import LLMCevabi, LLMHatasi

ANAHTAR = "gercek-gibi-anahtar-987654"


class SahteIstemci:
    def __init__(self, ayarlar, butce=None):
        self.model = ayarlar.model
        self.butce = butce

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
        if self.butce:
            self.butce.harca()
        if parca_gelince:
            parca_gelince("Şirket ")
            parca_gelince("özeti")
        return LLMCevabi("Şirket özeti", 50, 5, 1, model=self.model)


@pytest.fixture
def ortam(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", ANAHTAR)
    monkeypatch.setenv("LLM_BASE_URL", "https://sahte.local/v1")
    monkeypatch.setenv("LLM_MODEL", "sahte")


def belge_yaz(tmp_path, metin="Uzun bir Türkçe belge.", ad="belge.txt"):
    yol = tmp_path / ad
    yol.write_text(metin, encoding="utf-8")
    return yol


def test_uctan_uca_json(tmp_path, monkeypatch, capsys, ortam):
    monkeypatch.setenv("LLM_GIRDI_FIYATI", "0,30")  # Türkçe virgül de kabul
    monkeypatch.setenv("LLM_CIKTI_FIYATI", "2.5")
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)

    belge = belge_yaz(tmp_path)
    assert cli.main([str(belge)]) == cli.BASARILI

    ham = (tmp_path / "belge.ozet.json").read_text(encoding="utf-8")
    veri = json.loads(ham)
    assert veri["ozet"] == "Şirket özeti"
    assert veri["kaynak_dosya"] == "belge.txt"
    assert veri["maliyet_usd"] == round((50 * 0.30 + 5 * 2.5) / 1e6, 6)
    assert "Şirket" in ham  # ş değil
    # Sızıntı: JSON'da anahtar, belge metni veya tam yol olmamalı
    assert ANAHTAR not in ham and "Uzun bir Türkçe belge" not in ham and str(tmp_path) not in ham
    assert "Şirket özeti" in capsys.readouterr().out


def test_eksik_ayar_anlamli_hata(tmp_path, capsys):
    assert cli.main([str(belge_yaz(tmp_path))]) == cli.HATA
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_yer_tutucu_anahtar_yakalanir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "buraya-anahtarini-yaz")
    monkeypatch.setenv("LLM_BASE_URL", "https://sahte.local/v1")
    monkeypatch.setenv("LLM_MODEL", "sahte")
    assert cli.main([str(belge_yaz(tmp_path))]) == cli.HATA
    assert "örnek değerde" in capsys.readouterr().err


def test_kisisel_veri_varsa_gondermeden_durur(tmp_path, monkeypatch, capsys, ortam):
    gonderildi = []
    monkeypatch.setattr(cli, "LLMIstemcisi", lambda a, **k: gonderildi.append(1) or SahteIstemci(a, **k))
    belge = belge_yaz(tmp_path, "Müşteri e-postası ali.veli@example.com, IBAN TR33 0006 1005 1978 6457 8413 26")
    assert cli.main([str(belge)]) == cli.KISISEL_VERI
    hata = capsys.readouterr().err
    assert "kişisel veri" in hata and "e-posta" in hata and "IBAN" in hata
    assert "ali.veli" not in hata  # bulunan değerin kendisi ekrana basılmaz
    assert gonderildi == []  # sağlayıcıya hiç istek gitmedi
    assert not (tmp_path / "belge.ozet.json").exists()


def test_yine_de_gonder_ile_devam_eder(tmp_path, monkeypatch, ortam):
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)
    belge = belge_yaz(tmp_path, "İletişim: ali.veli@example.com")
    assert cli.main([str(belge), "--yine-de-gonder", "--akissiz"]) == cli.BASARILI


def test_hata_mesajinda_anahtar_gizlenir(tmp_path, monkeypatch, capsys, ortam):
    class SizdiranIstemci(SahteIstemci):
        def tamamla(self, *a, **k):
            raise LLMHatasi(f"sunucu şunu döndürdü: Bearer {ANAHTAR}")

    monkeypatch.setattr(cli, "LLMIstemcisi", SizdiranIstemci)
    assert cli.main([str(belge_yaz(tmp_path))]) == cli.HATA
    cikti = capsys.readouterr()
    assert ANAHTAR not in cikti.err + cikti.out
    assert "gerc***" in cikti.err


def test_akis_sifirlaninca_kullanici_uyarilir(tmp_path, monkeypatch, capsys, ortam):
    class KopanIstemci(SahteIstemci):
        def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
            parca_gelince("Yarım")
            akis_sifirlandi()
            parca_gelince("Tam özet")
            return LLMCevabi("Tam özet", 1, 1, 2, model=self.model)

    monkeypatch.setattr(cli, "LLMIstemcisi", KopanIstemci)
    assert cli.main([str(belge_yaz(tmp_path))]) == cli.BASARILI
    assert "yarım cevabı yok say" in capsys.readouterr().err
    veri = json.loads((tmp_path / "belge.ozet.json").read_text(encoding="utf-8"))
    assert veri["ozet"] == "Tam özet"


@pytest.mark.parametrize("argumanlar", [
    ["--temperature", "5"],
    ["--temperature", "abc"],
    ["--top-p", "0"],
    ["--max-token", "-1"],
    ["--uzunluk", "dev"],
])
def test_gecersiz_argumanlar_reddedilir(tmp_path, argumanlar, capsys):
    with pytest.raises(SystemExit) as bilgi:
        cli.main([str(belge_yaz(tmp_path)), *argumanlar])
    assert bilgi.value.code == 2  # argparse kullanım hatası


def test_turkce_virgullu_sayi_kabul_edilir(tmp_path, monkeypatch, ortam):
    alinan = {}

    class Kaydeden(SahteIstemci):
        def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
            alinan["t"] = uretim.temperature
            return super().tamamla(sistem, kullanici, uretim, parca_gelince, akis_sifirlandi)

    monkeypatch.setattr(cli, "LLMIstemcisi", Kaydeden)
    assert cli.main([str(belge_yaz(tmp_path)), "--temperature", "0,7"]) == cli.BASARILI
    assert alinan["t"] == 0.7


def test_word_dosyasi_ve_okuma_notlari_jsonda(tmp_path, monkeypatch, ortam):
    from docx import Document
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)
    d = Document(); d.add_paragraph("Bütçe onaylandı.")
    yol = tmp_path / "karar.docx"; d.save(yol)
    assert cli.main([str(yol), "--akissiz"]) == cli.BASARILI
    veri = json.loads((tmp_path / "karar.ozet.json").read_text(encoding="utf-8"))
    assert veri["belge_turu"] == "word" and veri["saglayiciya_gonderilen_gorsel"] == 0


def test_gemini_ocr_uyarisi(tmp_path, monkeypatch, capsys, ortam):
    import io
    from PIL import Image

    class GorenIstemci(SahteIstemci):
        okuma_girdi_token = 7
        okuma_cikti_token = 2
        def gorseli_metne_cevir(self, png):
            return "Fiş toplamı 120 TL"

        def sesi_metne_cevir(self, wav):
            raise AssertionError("ses gönderilmemeli")

    monkeypatch.setattr(cli, "LLMIstemcisi", GorenIstemci)
    yol = tmp_path / "fis.png"
    Image.new("RGB", (200, 80), "white").save(yol)
    assert cli.main([str(yol), "--ocr", "gemini"]) == cli.BASARILI
    assert "kişisel veri kontrolünden önce" in capsys.readouterr().err
    veri = json.loads((tmp_path / "fis.ozet.json").read_text(encoding="utf-8"))
    assert veri["saglayiciya_gonderilen_gorsel"] == 1 and veri["okuma_girdi_token"] == 7


def test_env_dosyasi_okumadan_once_yuklenir(tmp_path, monkeypatch):
    """TESSERACT_YOLU gibi ayarlar dosya okunmadan önce .env'den gelmeli."""
    sira = []
    monkeypatch.setattr("ozetleyici.ayarlar.load_dotenv", lambda: sira.append("env"))
    gercek = cli.belge_dosyasini_oku
    monkeypatch.setattr(cli, "belge_dosyasini_oku", lambda *a, **k: sira.append("oku") or gercek(*a, **k))
    cli.main([str(belge_yaz(tmp_path))])
    assert sira[:2] == ["env", "oku"]



def test_butce_asilirsa_hic_istek_gitmeden_durur(tmp_path, monkeypatch, capsys, ortam):
    istekler = []

    class Sayan(SahteIstemci):
        def tamamla(self, *a, **k):
            istekler.append(1)
            return super().tamamla(*a, **k)

    monkeypatch.setattr(cli, "LLMIstemcisi", Sayan)
    uzun = "\n\n".join(["Uzun bir paragraf. " * 300] * 30)  # ~170.000 karakter -> ~16 istek
    belge = belge_yaz(tmp_path, uzun)
    assert cli.main([str(belge), "--istek-siniri", "5"]) == cli.BUTCE
    hata = capsys.readouterr().err
    assert "API isteği gerektiriyor" in hata and "--istek-siniri" in hata
    assert istekler == []  # tek bir istek bile gönderilmedi


def test_butce_yukseltilince_devam_eder(tmp_path, monkeypatch, ortam):
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)
    uzun = "\n\n".join(["Uzun bir paragraf. " * 300] * 30)
    belge = belge_yaz(tmp_path, uzun)
    assert cli.main([str(belge), "--istek-siniri", "100", "--akissiz"]) == cli.BASARILI
    veri = json.loads((tmp_path / "belge.ozet.json").read_text(encoding="utf-8"))
    assert veri["kullanilan_istek"] == veri["istek_sayisi"] > 5


def test_varsayilan_sinir_env_den(tmp_path, monkeypatch, ortam):
    monkeypatch.setenv("LLM_EN_FAZLA_ISTEK", "3")
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)
    uzun = "\n\n".join(["Uzun bir paragraf. " * 300] * 30)
    assert cli.main([str(belge_yaz(tmp_path, uzun))]) == cli.BUTCE


def test_ses_dosyasi_yerel_olarak_ozetlenir(tmp_path, monkeypatch, ortam):
    from ozetleyici.okuyucular import medya
    from tests.medya_uret import ses_dosyasi
    monkeypatch.setattr(medya, "yerel_yazi_dok", lambda pcm, model: f"[00:00] Bütçe onaylandı. ({model})")
    olusan = []
    monkeypatch.setattr(cli, "LLMIstemcisi", lambda a, **k: olusan.append(1) or SahteIstemci(a, **k))
    yol = tmp_path / "toplanti.mp3"
    yol.write_bytes(ses_dosyasi("mp3", "libmp3lame", saniye=2))
    assert cli.main([str(yol), "--akissiz", "--whisper-modeli", "base"]) == cli.BASARILI
    veri = json.loads((tmp_path / "toplanti.ozet.json").read_text(encoding="utf-8"))
    assert veri["belge_turu"] == "ses" and veri["ses_suresi_sn"] >= 1.8
    assert veri["saglayiciya_gonderilen_ses_parcasi"] == 0
    assert any("Whisper base" in n for n in veri["okuma_notlari"])


def test_gecersiz_whisper_modeli_env(tmp_path, monkeypatch, capsys, ortam):
    from tests.medya_uret import ses_dosyasi
    monkeypatch.setenv("WHISPER_MODELI", "kotu/depo")
    yol = tmp_path / "a.wav"
    yol.write_bytes(ses_dosyasi("wav", "pcm_s16le", saniye=1))
    assert cli.main([str(yol)]) == cli.HATA
    assert "WHISPER_MODELI" in capsys.readouterr().err



def test_modelleri_listele(monkeypatch, capsys, ortam):
    class Listeleyen(SahteIstemci):
        def modelleri_listele(self):
            return ["gemini-x-pro", "sahte", "gemini-embedding-001", "gemini-x-flash"]

    monkeypatch.setattr(cli, "LLMIstemcisi", Listeleyen)
    assert cli.main(["--modelleri-listele"]) == cli.BASARILI
    cikti = capsys.readouterr().out
    assert cikti.splitlines()[:3] == ["sahte  (varsayılan)", "gemini-x-flash", "gemini-x-pro"]
    assert "embedding" not in cikti and "rate-limit" in cikti


def test_dosya_verilmezse_kullanim_hatasi():
    with pytest.raises(SystemExit) as bilgi:
        cli.main([])
    assert bilgi.value.code == 2


def test_odak_secenegi(tmp_path, monkeypatch, ortam):
    sistemler = []

    class Kaydeden(SahteIstemci):
        def tamamla(self, sistem, *a, **k):
            sistemler.append(sistem)
            return super().tamamla(sistem, *a, **k)

    monkeypatch.setattr(cli, "LLMIstemcisi", Kaydeden)
    assert cli.main([str(belge_yaz(tmp_path)), "--odak", "bütçe", "--akissiz"]) == cli.BASARILI
    assert "<odak>bütçe</odak>" in sistemler[0]
    with pytest.raises(SystemExit):
        cli.main([str(belge_yaz(tmp_path)), "--odak", "x" * 301])
