import pytest


@pytest.fixture(autouse=True)
def ortam_degiskenlerini_temizle(monkeypatch):
    """Bilgisayardaki gerçek .env veya ortam değişkenleri testleri etkilemesin."""
    for ad in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_GIRDI_FIYATI", "LLM_CIKTI_FIYATI"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr("ozetleyici.ayarlar.load_dotenv", lambda: None)
