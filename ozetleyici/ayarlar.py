"""Ayarları ortam değişkenlerinden (ve varsa .env dosyasından) okur."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


YER_TUTUCU_ANAHTAR = "buraya-anahtarini-yaz"  # .env.example'daki örnek değer


class AyarHatasi(Exception):
    """Eksik veya hatalı ayar."""


@dataclass(frozen=True)
class Ayarlar:
    api_anahtari: str
    base_url: str
    model: str
    girdi_fiyati: float | None = None  # USD / 1 milyon token
    cikti_fiyati: float | None = None


def ayarlari_yukle() -> Ayarlar:
    # .env dosyasındaki satırları ortam değişkeni gibi yükler.
    # Terminalde zaten tanımlı bir değişken varsa onu ezmez.
    load_dotenv()

    eksikler = [ad for ad in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not os.getenv(ad)]
    if eksikler:
        raise AyarHatasi(
            "Eksik ayar: " + ", ".join(eksikler)
            + ". .env.example dosyasını .env adıyla kopyalayıp doldur."
        )

    if os.environ["LLM_API_KEY"].strip() == YER_TUTUCU_ANAHTAR:
        raise AyarHatasi(
            "LLM_API_KEY hâlâ örnek değerde. .env dosyasına gerçek API anahtarını yazıp kaydet."
        )

    return Ayarlar(
        api_anahtari=os.environ["LLM_API_KEY"].strip(),
        base_url=os.environ["LLM_BASE_URL"],
        model=os.environ["LLM_MODEL"],
        girdi_fiyati=_sayi_oku("LLM_GIRDI_FIYATI"),
        cikti_fiyati=_sayi_oku("LLM_CIKTI_FIYATI"),
    )


def _sayi_oku(ad: str) -> float | None:
    deger = os.getenv(ad)
    if not deger:
        return None
    try:
        return float(deger.replace(",", "."))
    except ValueError as hata:
        raise AyarHatasi(f"{ad} bir sayı olmalı, gelen: {deger!r}") from hata
