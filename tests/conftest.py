import pytest


@pytest.fixture(autouse=True)
def ortam_degiskenlerini_temizle(monkeypatch, request):
    """Bilgisayardaki gerçek .env veya ortam değişkenleri testleri etkilemesin.

    Gerçek API testi (gercek_api işaretli) bu temizlikten muaftır.
    """
    if request.node.get_closest_marker("gercek_api"):
        return
    for ad in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_YEDEK_MODEL", "LLM_ZAMAN_ASIMI",
               "LLM_GIRDI_FIYATI", "LLM_CIKTI_FIYATI", "LLM_EN_FAZLA_ISTEK", "LLM_EMBEDDING_MODELI"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setattr("ozetleyici.ayarlar.load_dotenv", lambda: None)
