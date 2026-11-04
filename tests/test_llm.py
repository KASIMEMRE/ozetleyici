"""LLM istemcisini sahte bir HTTP sunucusuna karşı test eder (internet ve anahtar gerekmez)."""

import json

import httpx2
import openai
import pytest

from ozetleyici.ayarlar import Ayarlar
from ozetleyici.llm import LLMHatasi, LLMIstemcisi, UretimAyarlari

AYAR = Ayarlar(api_anahtari="test", base_url="https://sahte.local/v1", model="m")


def cevap_govdesi(metin="Merhaba"):
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": metin}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }


def istemci_kur(isleyici, monkeypatch):
    monkeypatch.setattr("ozetleyici.llm.time.sleep", lambda s: None)  # testte bekleme
    ist = LLMIstemcisi(AYAR)
    ist._istemci = openai.OpenAI(
        api_key="test", base_url=AYAR.base_url, max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(isleyici)),
    )
    return ist


def test_basarili_cevap_ve_token(monkeypatch):
    gonderilen = {}

    def isleyici(istek):
        gonderilen.update(json.loads(istek.content))
        return httpx2.Response(200, json=cevap_govdesi("Özet hazır"))

    cevap = istemci_kur(isleyici, monkeypatch).tamamla("sis", "kul", UretimAyarlari())
    assert cevap.metin == "Özet hazır"
    assert (cevap.girdi_token, cevap.cikti_token) == (12, 3)
    # Verilmeyen örnekleme ayarları API'ye hiç gönderilmemeli
    assert "temperature" not in gonderilen and "top_p" not in gonderilen
    assert gonderilen["messages"][0] == {"role": "system", "content": "sis"}


def test_temperature_verilirse_gonderilir(monkeypatch):
    gonderilen = {}

    def isleyici(istek):
        gonderilen.update(json.loads(istek.content))
        return httpx2.Response(200, json=cevap_govdesi())

    istemci_kur(isleyici, monkeypatch).tamamla("s", "k", UretimAyarlari(temperature=0.2))
    assert gonderilen["temperature"] == 0.2


def test_429_sonra_yeniden_dener(monkeypatch):
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        if sayac["n"] < 3:
            return httpx2.Response(429, json={"error": {"message": "yavaş"}})
        return httpx2.Response(200, json=cevap_govdesi())

    cevap = istemci_kur(isleyici, monkeypatch).tamamla("s", "k", UretimAyarlari())
    assert cevap.deneme_sayisi == 3


def test_surekli_500_sonunda_vazgecer(monkeypatch):
    isleyici = lambda istek: httpx2.Response(500, json={"error": {"message": "çöktü"}})
    with pytest.raises(LLMHatasi, match="4 denemeden sonra"):
        istemci_kur(isleyici, monkeypatch).tamamla("s", "k", UretimAyarlari())


def test_401_hemen_anlamli_hata(monkeypatch):
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        return httpx2.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(LLMHatasi, match="anahtarı geçersiz"):
        istemci_kur(isleyici, monkeypatch).tamamla("s", "k", UretimAyarlari())
    assert sayac["n"] == 1  # 401'de yeniden denemek anlamsız


def test_akis_halinde_cevap(monkeypatch):
    parcalar = ["Mer", "ha", "ba"]
    satirlar = []
    for p in parcalar:
        satirlar.append({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                         "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]})
    satirlar.append({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m", "choices": [],
                     "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})
    govde = "".join(f"data: {json.dumps(s)}\n\n" for s in satirlar) + "data: [DONE]\n\n"

    isleyici = lambda istek: httpx2.Response(200, content=govde.encode(),
                                             headers={"content-type": "text/event-stream"})
    gelen = []
    cevap = istemci_kur(isleyici, monkeypatch).tamamla("s", "k", UretimAyarlari(), parca_gelince=gelen.append)
    assert gelen == parcalar
    assert cevap.metin == "Merhaba"
    assert cevap.cikti_token == 3
