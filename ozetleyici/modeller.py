"""Sağlayıcının model listesini özetleme için uygun olanlara indirger."""

from __future__ import annotations

# Ad parçasına göre elenen modeller: metin üretmeyen ya da özetlemeye yaramayanlar.
ELENENLER = (
    "embedding", "tts", "live", "transcribe", "translate", "lyria", "robotics",
    "nano-banana", "imagen", "veo", "image", "omni", "aqa", "audio", "realtime", "whisper",
    "moderation", "dall-e", "search",
)


def ozet_modelleri(adlar: list[str], varsayilan: str) -> list[str]:
    """Metin üretebilen modelleri döndürür; varsayılan model her zaman başta."""
    uygun = [a for a in adlar if not any(e in a.lower() for e in ELENENLER)]

    def sira(ad: str) -> tuple:
        a = ad.lower()
        # önce hafif ve hızlı modeller (ücretsiz katmanda genelde daha bol kotalı), sonra büyükler
        grup = 0 if "lite" in a else 1 if "flash" in a else 2 if "pro" in a else 3
        return (grup, "preview" in a or "exp" in a, a)

    sonuc = sorted(set(uygun) - {varsayilan}, key=sira)
    return [varsayilan, *sonuc]
