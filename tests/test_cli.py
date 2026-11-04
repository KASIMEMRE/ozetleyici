import json

from ozetleyici import __main__ as cli
from ozetleyici.llm import LLMCevabi


class SahteIstemci:
    def __init__(self, ayarlar):
        self.model = ayarlar.model

    def tamamla(self, sistem, kullanici, uretim, parca_gelince=None):
        if parca_gelince:
            parca_gelince("Şirket ")
            parca_gelince("özeti")
        return LLMCevabi("Şirket özeti", 50, 5, 1)


def test_uctan_uca_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_BASE_URL", "https://sahte.local/v1")
    monkeypatch.setenv("LLM_MODEL", "sahte")
    monkeypatch.setenv("LLM_GIRDI_FIYATI", "0,30")  # Türkçe virgül de kabul
    monkeypatch.setenv("LLM_CIKTI_FIYATI", "2.5")
    monkeypatch.setattr(cli, "LLMIstemcisi", SahteIstemci)

    belge = tmp_path / "belge.txt"
    belge.write_text("Uzun bir Türkçe belge.", encoding="utf-8")
    assert cli.main([str(belge)]) == 0

    veri = json.loads((tmp_path / "belge.ozet.json").read_text(encoding="utf-8"))
    assert veri["ozet"] == "Şirket özeti"
    assert veri["kaynak_dosya"] == "belge.txt"
    assert veri["maliyet_usd"] == round((50 * 0.30 + 5 * 2.5) / 1e6, 6)
    assert "Şirket" in (tmp_path / "belge.ozet.json").read_text(encoding="utf-8")  # ş değil
    assert "Şirket özeti" in capsys.readouterr().out


def test_eksik_ayar_anlamli_hata(tmp_path, capsys):
    belge = tmp_path / "b.txt"
    belge.write_text("metin", encoding="utf-8")
    assert cli.main([str(belge)]) == 1
    assert "LLM_API_KEY" in capsys.readouterr().err
