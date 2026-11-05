"""Ayarları ortam değişkenlerinden (ve varsa .env dosyasından) okur."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

YER_TUTUCU_ANAHTAR = "buraya-anahtarini-yaz"  # .env.example'daki örnek değer


class AyarHatasi(Exception):
    """Eksik veya hatalı ayar."""


@dataclass(frozen=True)
class Ayarlar:
    # repr=False: Ayarlar nesnesi yazdırılırsa veya bir hata mesajına karışırsa
    # anahtar görünmesin.
    api_anahtari: str = field(repr=False)
    base_url: str
    model: str
    yedek_model: str | None = None
    zaman_asimi_sn: float = 60.0
    girdi_fiyati: float | None = None  # USD / 1 milyon token
    cikti_fiyati: float | None = None


def ayarlari_yukle() -> Ayarlar:
    # .env dosyasındaki satırları ortam değişkeni gibi yükler.
    # Terminalde zaten tanımlı bir değişken varsa onu ezmez.
    load_dotenv()

    eksikler = [ad for ad in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not os.getenv(ad, "").strip()]
    if eksikler:
        raise AyarHatasi(
            "Eksik ayar: " + ", ".join(eksikler)
            + ". .env.example dosyasını .env adıyla kopyalayıp doldur."
        )

    anahtar = os.environ["LLM_API_KEY"].strip().strip('"').strip("'")
    if anahtar == YER_TUTUCU_ANAHTAR:
        raise AyarHatasi("LLM_API_KEY hâlâ örnek değerde. .env dosyasına gerçek API anahtarını yazıp kaydet.")

    zaman_asimi = _sayi_oku("LLM_ZAMAN_ASIMI")
    if zaman_asimi is not None and not 5 <= zaman_asimi <= 600:
        raise AyarHatasi("LLM_ZAMAN_ASIMI 5 ile 600 saniye arasında olmalı.")

    return Ayarlar(
        api_anahtari=anahtar,
        base_url=os.environ["LLM_BASE_URL"].strip(),
        model=os.environ["LLM_MODEL"].strip(),
        yedek_model=os.getenv("LLM_YEDEK_MODEL", "").strip() or None,
        zaman_asimi_sn=zaman_asimi if zaman_asimi is not None else 60.0,
        girdi_fiyati=_sayi_oku("LLM_GIRDI_FIYATI"),
        cikti_fiyati=_sayi_oku("LLM_CIKTI_FIYATI"),
    )


def anahtari_gizle(metin: str, anahtar: str | None) -> str:
    """Bir metnin içinde API anahtarı geçiyorsa onu *** ile değiştirir.

    Hata mesajları bazen isteğin ayrıntılarını içerir; ekrana veya log'a
    basmadan önce anahtarın sızmadığından emin oluyoruz.
    """
    if not anahtar or len(anahtar) < 8:
        return metin
    return metin.replace(anahtar, f"{anahtar[:4]}***")


def _sayi_oku(ad: str) -> float | None:
    deger = os.getenv(ad, "").strip()
    if not deger:
        return None
    try:
        sayi = float(deger.replace(",", "."))
    except ValueError as hata:
        raise AyarHatasi(f"{ad} bir sayı olmalı, gelen: {deger!r}") from hata
    if sayi < 0:
        raise AyarHatasi(f"{ad} negatif olamaz.")
    return sayi
