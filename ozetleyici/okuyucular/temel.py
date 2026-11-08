"""Okuyucuların ortak parçaları: hata türü, sonuç, metin temizliği ve dosya güvenliği."""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import Callable


class OkumaHatasi(Exception):
    """Dosya okunamadığında kullanıcıya gösterilecek anlamlı hata."""


@dataclass
class OkumaSonucu:
    metin: str
    tur: str                                         # "pdf", "word", "excel" ...
    notlar: list[str] = field(default_factory=list)  # kullanıcıya gösterilecek bilgiler
    ocr_sayfa_sayisi: int = 0
    disari_gonderilen_gorsel: int = 0                # Gemini ile okunan görsel sayısı
    ses_suresi_sn: float = 0.0
    disari_gonderilen_ses_parcasi: int = 0           # Gemini'ye gönderilen 5 dakikalık ses parçası


@dataclass(frozen=True)
class OcrAyari:
    """Taranmış sayfaların, görsellerin ve ses/video kayıtlarının nasıl okunacağı.

    kip: "yerel"  -> Tesseract, görüntü bilgisayardan çıkmaz
         "gemini" -> görüntü LLM sağlayıcısına gönderilir (daha iyi okur)
         "kapali" -> OCR yapılmaz
    """

    kip: str = "yerel"
    dil: str = "tur"
    # Gemini kipinde: (png baytları) -> metin. LLM istemcisi tarafından sağlanır.
    gorsel_okuyucu: Callable[[bytes], str] | None = None
    en_fazla_sayfa: int = 30
    # Sağlayıcıya istek göndermeden önce kaç istek gerekeceğini bildirir;
    # bütçeyi aşıyorsa hata fırlatıp işi başlamadan durdurur.
    on_kontrol: Callable[[int], None] | None = None
    # Ses ve video: "yerel" -> faster-whisper (ses bilgisayardan çıkmaz), "gemini" -> sağlayıcıya gönderilir
    ses_kipi: str = "yerel"
    ses_okuyucu: Callable[[bytes], str] | None = None          # Gemini kipinde: WAV baytları -> metin
    transkriptor: Callable[[bytes, str], str] | None = None    # yerel kipte yerine geçecek fonksiyon (testler)
    whisper_modeli: str = "small"
    en_uzun_ses_sn: int = 3600

    def __post_init__(self) -> None:
        if self.kip not in ("yerel", "gemini", "kapali"):
            raise ValueError(f"Geçersiz OCR kipi: {self.kip}")
        if self.ses_kipi not in ("yerel", "gemini"):
            raise ValueError(f"Geçersiz ses kipi: {self.ses_kipi}")


# ---------------------------------------------------------------- metin temizliği

# Görünmez karakterler: sıfır genişlikli boşluklar ve yazı yönünü değiştiren
# işaretler. İnsan göremez ama model okur; belgeye gizli talimat saklamak için
# kullanılabilir (prompt injection). Bu yüzden temizliyoruz.
_GORUNMEZ = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿­]")
_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def metni_temizle(metin: str, notlar: list[str] | None = None) -> str:
    # PDF'lerde "ş" bazen "s" + birleştirici işaret olarak iki karakter gelir.
    # NFC normalleştirmesi bunları tek karaktere birleştirir.
    metin = unicodedata.normalize("NFC", metin)
    gorunmez = len(_GORUNMEZ.findall(metin))
    metin = _GORUNMEZ.sub("", metin)
    metin = _KONTROL.sub("", metin)
    if gorunmez and notlar is not None:
        notlar.append(f"{gorunmez} görünmez karakter temizlendi.")
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")
    satirlar = [satir.rstrip() for satir in metin.split("\n")]
    temiz = "\n".join(satirlar)
    temiz = re.sub(r"\n{3,}", "\n\n", temiz)
    return temiz.strip()


# ---------------------------------------------------------------- dosya güvenliği

# Dosyanın gerçek türü uzantısından değil, ilk baytlarından ("sihirli sayı") anlaşılır.
IMZALAR = {
    "pdf": (b"%PDF",),
    "zip": (b"PK\x03\x04",),          # .docx, .xlsx, .pptx aslında zip arşividir
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
}


def imzayi_dogrula(veri: bytes, beklenen: str, ad: str) -> None:
    if not veri.startswith(IMZALAR[beklenen]):
        raise OkumaHatasi(
            f"{ad}: dosyanın içeriği uzantısıyla uyuşmuyor (beklenen: {beklenen}). "
            "Dosya bozuk olabilir ya da türü gizlenmiş olabilir."
        )


# Zip bombası sınırları: küçük bir dosya açılınca gigabaytlara şişmesin.
ZIP_EN_FAZLA_ACIK_BOYUT = 200 * 1024 * 1024   # toplam açılmış boyut
ZIP_EN_FAZLA_DOSYA = 5_000
ZIP_EN_FAZLA_ORAN = 200                         # açılmış / sıkıştırılmış


def zip_guvenligini_dogrula(veri: bytes, ad: str) -> None:
    try:
        arsiv = zipfile.ZipFile(io.BytesIO(veri))
    except zipfile.BadZipFile as hata:
        raise OkumaHatasi(f"{ad}: dosya bozuk (geçerli bir Office dosyası değil).") from hata
    girdiler = arsiv.infolist()
    if len(girdiler) > ZIP_EN_FAZLA_DOSYA:
        raise OkumaHatasi(f"{ad}: dosya alışılmadık sayıda parça içeriyor ({len(girdiler)}); güvenlik için reddedildi.")
    toplam = sum(g.file_size for g in girdiler)
    sikistirilmis = max(sum(g.compress_size for g in girdiler), 1)
    if toplam > ZIP_EN_FAZLA_ACIK_BOYUT or (toplam > 10 * 1024 * 1024 and toplam / sikistirilmis > ZIP_EN_FAZLA_ORAN):
        raise OkumaHatasi(
            f"{ad}: açıldığında {toplam / 1e6:.0f} MB'a şişiyor (sıkıştırma oranı {toplam / sikistirilmis:.0f}x). "
            "Zip bombası olabilir; güvenlik için reddedildi."
        )
    for g in girdiler:
        if g.filename.startswith(("/", "\\")) or ".." in g.filename.replace("\\", "/").split("/"):
            raise OkumaHatasi(f"{ad}: arşivde şüpheli dosya yolu var; güvenlik için reddedildi.")


def metin_kodunu_coz(veri: bytes, ad: str) -> str:
    # "utf-8-sig" Notepad'in eklediği BOM işaretini atar; "cp1254" eski Windows Türkçesidir.
    for kodlama in ("utf-8-sig", "cp1254"):
        try:
            return veri.decode(kodlama)
        except UnicodeDecodeError:
            continue
    raise OkumaHatasi(f"{ad}: karakter kodlaması çözülemedi.")
