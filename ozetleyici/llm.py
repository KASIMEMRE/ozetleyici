"""LLM API istemcisi: OpenAI uyumlu her sağlayıcıyla çalışır.

Gemini, Claude, OpenAI ve Ollama aynı "chat completions" biçimini
destekler; sağlayıcıyı değiştirmek için yalnızca .env'deki adres,
anahtar ve model adını değiştirmek yeterli.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

import openai

from .ayarlar import Ayarlar


class LLMHatasi(Exception):
    """API'den kaynaklanan, kullanıcıya gösterilecek hata."""


@dataclass
class LLMCevabi:
    metin: str
    girdi_token: int | None
    cikti_token: int | None
    deneme_sayisi: int


@dataclass
class UretimAyarlari:
    """Modelin nasıl metin üreteceğini belirleyen örnekleme ayarları.

    None olan ayar API'ye hiç gönderilmez; sağlayıcının varsayılanı kullanılır.
    Bazı modeller (ör. yeni Claude modelleri) temperature/top_p kabul etmez.
    """

    temperature: float | None = None
    top_p: float | None = None
    max_token: int = 1024


# Bu hatalar geçicidir: biraz bekleyip yeniden denemek mantıklı.
GECICI_HATALAR = (
    openai.RateLimitError,       # 429: çok hızlı istek attın
    openai.InternalServerError,  # 5xx: sağlayıcı tarafında sorun
    openai.APIConnectionError,   # internet/bağlantı sorunu (zaman aşımı dahil)
)


class LLMIstemcisi:
    def __init__(self, ayarlar: Ayarlar, en_fazla_deneme: int = 4) -> None:
        self.model = ayarlar.model
        self.en_fazla_deneme = en_fazla_deneme
        # max_retries=0: yeniden denemeyi kütüphaneye bırakmıyoruz,
        # aşağıda kendimiz yazıyoruz ki nasıl çalıştığını görelim.
        self._istemci = openai.OpenAI(
            api_key=ayarlar.api_anahtari,
            base_url=ayarlar.base_url,
            max_retries=0,
            timeout=120,
        )

    def tamamla(
        self,
        sistem: str,
        kullanici: str,
        uretim: UretimAyarlari,
        parca_gelince: Callable[[str], None] | None = None,
    ) -> LLMCevabi:
        """Modele bir istek gönderir. parca_gelince verilirse cevap akış halinde gelir."""
        mesajlar = [
            {"role": "system", "content": sistem},
            {"role": "user", "content": kullanici},
        ]
        parametreler: dict = {"model": self.model, "messages": mesajlar, "max_tokens": uretim.max_token}
        if uretim.temperature is not None:
            parametreler["temperature"] = uretim.temperature
        if uretim.top_p is not None:
            parametreler["top_p"] = uretim.top_p

        for deneme in range(1, self.en_fazla_deneme + 1):
            try:
                if parca_gelince is None:
                    return self._tek_seferde(parametreler, deneme)
                return self._akis_halinde(parametreler, deneme, parca_gelince)
            except openai.AuthenticationError as hata:  # 401
                raise LLMHatasi("API anahtarı geçersiz (401). .env içindeki LLM_API_KEY'i kontrol et.") from hata
            except openai.NotFoundError as hata:  # 404
                raise LLMHatasi(f"Model veya adres bulunamadı (404): model={self.model!r}. LLM_MODEL ve LLM_BASE_URL'i kontrol et.") from hata
            except openai.BadRequestError as hata:  # 400
                ayrinti = _hata_ayrintisi(hata)
                if "api key" in ayrinti.lower() or "api_key" in ayrinti.lower():
                    # Gemini geçersiz anahtara 401 değil 400 döndürür.
                    raise LLMHatasi(f"API anahtarı geçersiz (400). .env içindeki LLM_API_KEY'i kontrol et. Sağlayıcı: {ayrinti}") from hata
                raise LLMHatasi(f"İstek reddedildi (400): {ayrinti}") from hata
            except GECICI_HATALAR as hata:
                if deneme == self.en_fazla_deneme:
                    ayrinti = _hata_ayrintisi(hata) if isinstance(hata, openai.APIStatusError) else str(hata)
                    raise LLMHatasi(f"{deneme} denemeden sonra vazgeçildi ({type(hata).__name__}): {ayrinti}") from hata
                bekleme = _bekleme_suresi(deneme, hata)
                print(f"[uyarı] Geçici hata ({type(hata).__name__}). {bekleme:.1f} sn sonra yeniden deneniyor ({deneme}/{self.en_fazla_deneme})...")
                time.sleep(bekleme)
        raise AssertionError("buraya ulaşılmamalı")

    def _tek_seferde(self, parametreler: dict, deneme: int) -> LLMCevabi:
        cevap = self._istemci.chat.completions.create(**parametreler)
        kullanim = cevap.usage
        return LLMCevabi(
            metin=cevap.choices[0].message.content or "",
            girdi_token=kullanim.prompt_tokens if kullanim else None,
            cikti_token=kullanim.completion_tokens if kullanim else None,
            deneme_sayisi=deneme,
        )

    def _akis_halinde(self, parametreler: dict, deneme: int, parca_gelince: Callable[[str], None]) -> LLMCevabi:
        akis = self._istemci.chat.completions.create(
            **parametreler, stream=True, stream_options={"include_usage": True}
        )
        parcalar: list[str] = []
        kullanim = None
        for parca in akis:
            if parca.usage:  # token bilgisi genelde son parçada gelir
                kullanim = parca.usage
            if parca.choices and parca.choices[0].delta.content:
                yazi = parca.choices[0].delta.content
                parcalar.append(yazi)
                parca_gelince(yazi)
        return LLMCevabi(
            metin="".join(parcalar),
            girdi_token=kullanim.prompt_tokens if kullanim else None,
            cikti_token=kullanim.completion_tokens if kullanim else None,
            deneme_sayisi=deneme,
        )


def _hata_ayrintisi(hata: openai.APIStatusError) -> str:
    """Sağlayıcının hata gövdesindeki açıklamayı çıkarır.

    Sağlayıcılar hatayı farklı biçimde döndürür: {"error": {...}}, [{"error": {...}}]
    veya düz metin. Bulamazsak ham gövdeyi gösteririz.
    """
    govde = hata.body
    if isinstance(govde, list) and govde:
        govde = govde[0]
    if isinstance(govde, dict):
        ic = govde.get("error", govde)
        if isinstance(ic, dict) and ic.get("message"):
            return str(ic["message"])
        if isinstance(ic, str):
            return ic
    try:
        metin = hata.response.text.strip()
    except Exception:
        metin = ""
    return metin[:500] or hata.message


def _bekleme_suresi(deneme: int, hata: Exception) -> float:
    # Sağlayıcı "şu kadar bekle" dediyse (Retry-After başlığı) ona uy.
    yanit = getattr(hata, "response", None)
    if yanit is not None:
        retry_after = yanit.headers.get("retry-after")
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                pass
    # Yoksa üstel geri çekilme: 1, 2, 4, 8 sn... + biraz rastgelelik (jitter).
    return min(2 ** (deneme - 1), 30) + random.uniform(0, 0.5)
