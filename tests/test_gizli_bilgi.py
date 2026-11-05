"""Depoda gizli anahtar olmadığını ve tarayıcının çalıştığını doğrular.

Örnek anahtarlar parçalar birleştirilerek üretilir; böylece bu test dosyası
kendisi taramaya takılmaz.
"""

import importlib.util
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gizli_tara", KOK / "scripts" / "gizli_tara.py")
gizli_tara = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gizli_tara)

SAHTE_GOOGLE = "AI" + "za" + "Sy" + "A" * 33
SAHTE_GOOGLE_YENI = "AQ" + "." + "Ab3_" * 12
SAHTE_ANTHROPIC = "sk-" + "ant-" + "api03-" + "x" * 30
SAHTE_OPENAI = "sk-" + "proj-" + "y" * 40


def test_depo_temiz():
    """Proje dosyalarının hiçbirinde gerçek anahtar yok (.env hariç; o depoya girmez)."""
    dosyalar = [(y, i) for y, i in gizli_tara._dosyalar(staged=False) if y != ".env"]
    assert gizli_tara.tara(dosyalar) == []


def test_env_example_yalnizca_yer_tutucu():
    icerik = (KOK / ".env.example").read_text(encoding="utf-8")
    assert gizli_tara.tara([(".env.example", icerik)]) == []
    assert "LLM_API_KEY=buraya-anahtarini-yaz" in icerik


def test_tarayici_anahtarlari_yakalar():
    for anahtar in (SAHTE_GOOGLE, SAHTE_GOOGLE_YENI, SAHTE_ANTHROPIC, SAHTE_OPENAI):
        bulgular = gizli_tara.tara([("a.py", f"x = '{anahtar}'")])
        assert bulgular, anahtar[:6]
        assert anahtar not in " ".join(bulgular)  # değerin tamamı ekrana basılmaz


def test_doldurulmus_env_example_yakalanir():
    bulgular = gizli_tara.tara([(".env.example", "LLM_API_KEY=benim-gizli-degerim\n")])
    assert any("Doldurulmuş LLM_API_KEY" in b for b in bulgular)


def test_yer_tutucu_ve_yorumlar_temiz():
    icerik = "LLM_API_KEY=buraya-anahtarini-yaz\n# LLM_API_KEY=sk-...\nLLM_API_KEY=ollama\n"
    assert gizli_tara.tara([(".env.example", icerik)]) == []


def test_env_dosyasinin_kendisi_yasak():
    for yol in (".env", ".env.local", "alt/.env.prod"):
        assert gizli_tara.tara([(yol, "")]), yol
    assert gizli_tara.tara([(".env.example", "")]) == []
