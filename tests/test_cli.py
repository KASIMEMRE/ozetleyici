import json

import pytest

from ozetleyici import __main__ as cli
from ozetleyici.llm import LLMCevabi, LLMHatasi

ANAHTAR = "gercek-gibi-anahtar-987654"


class SahteIstemci:
    def __init__(self, ayarlar):
        self.model = ayarlar.model

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None, akis_sifirlandi=None):
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
    monkeypatch.setattr(cli, "LLMIstemcisi", lambda a: gonderildi.append(1) or SahteIstemci(a))
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
