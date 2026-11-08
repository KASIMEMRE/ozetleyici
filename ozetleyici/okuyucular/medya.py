"""Ses ve video dosyalarındaki konuşmayı yazıya döker.

1. Dosya, ayrı bir süreçte (bkz. _ses_cozucu.py) 16 kHz mono sese çözülür.
2. Ses ya yerel olarak faster-whisper ile ya da (seçilirse) LLM sağlayıcısına
   gönderilerek yazıya dökülür.
Videoda yalnızca ses kanalı kullanılır; görüntü analiz edilmez.
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Callable

from .temel import OcrAyari, OkumaHatasi, OkumaSonucu, metni_temizle

log = logging.getLogger(__name__)

SES_UZANTILARI = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac"}
VIDEO_UZANTILARI = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

ORNEKLEME = 16_000
GEMINI_PARCA_SN = 300          # sağlayıcıya 5 dakikalık parçalar halinde gönderilir (istek boyutu sınırı)
COZME_ZAMAN_ASIMI_SN = 300     # çözücü süreç bu kadar sürede bitmezse durdurulur
COZUCU_BELLEK_SINIRI = 2 * 1024 ** 3  # Linux/macOS'ta çözücü sürecin bellek tavanı
COZUCU = Path(__file__).with_name("_ses_cozucu.py")

# Dosyanın gerçek türü ilk baytlarından anlaşılır (uzantı yalan söyleyebilir).
def _imza_turu(veri: bytes) -> str | None:
    if veri[:3] == b"ID3" or (len(veri) > 1 and veri[0] == 0xFF and veri[1] & 0xE0 == 0xE0):
        return "mp3"
    if veri[:4] == b"RIFF" and veri[8:12] == b"WAVE":
        return "wav"
    if veri[:4] == b"RIFF" and veri[8:12] == b"AVI ":
        return "avi"
    if veri[:4] == b"OggS":
        return "ogg"
    if veri[:4] == b"fLaC":
        return "flac"
    if veri[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "mp4"
    if veri[:4] == b"\x1aE\xdf\xa3":
        return "mkv"
    return None


BEKLENEN_IMZA = {
    ".mp3": {"mp3"}, ".wav": {"wav"}, ".m4a": {"mp4"}, ".ogg": {"ogg"}, ".opus": {"ogg"}, ".flac": {"flac"},
    ".mp4": {"mp4"}, ".mov": {"mp4"}, ".mkv": {"mkv"}, ".webm": {"mkv"}, ".avi": {"avi"},
}

# Whisper'ın Türkçede sessiz bölümlerde uydurduğu bilinen satırlar (eğitim verisindeki altyazı imzaları).
UYDURMA_SATIRLAR = {"altyazı m.k.", "altyazı m.k", "altyazı: m.k.", "altyazı m. k."}


def zaman(saniye: float) -> str:
    s = int(saniye)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _gizli_ortam_degiskeni(ad: str) -> bool:
    ad = ad.upper()
    return ad.startswith("LLM_") or any(k in ad for k in ("KEY", "TOKEN", "SECRET", "PASSWORD", "SIFRE"))


def sesi_coz(veri: bytes, ad: str, en_uzun_sn: float) -> tuple[bytes, float]:
    """Dosyayı ayrı süreçte 16 kHz mono 16 bit sese çözer: (ham ses, süre)."""
    # Çözücü süreç API anahtarlarını görmesin: bozuk bir dosya ffmpeg'de açık tetiklese bile
    # ele geçirilen süreç anahtara ulaşamaz.
    ortam = {k: v for k, v in os.environ.items() if not _gizli_ortam_degiskeni(k)}
    try:
        surec = subprocess.run(
            [sys.executable, "-I", str(COZUCU), str(en_uzun_sn), str(COZUCU_BELLEK_SINIRI), str(COZME_ZAMAN_ASIMI_SN)],
            input=veri, capture_output=True, timeout=COZME_ZAMAN_ASIMI_SN, env=ortam,
        )
    except subprocess.TimeoutExpired as hata:
        raise OkumaHatasi(f"{ad}: ses çözme {COZME_ZAMAN_ASIMI_SN} saniyede bitmedi; dosya bozuk olabilir.") from hata

    # Çözücü yalnızca ASCII JSON yazar; ffmpeg'in kendi uyarıları başka kodlamada olabilir.
    son_satir = (surec.stderr.decode("ascii", errors="replace").strip().splitlines() or [""])[-1]
    try:
        bilgi = json.loads(son_satir)
    except json.JSONDecodeError:
        bilgi = {}
    if surec.returncode != 0:
        mesaj = bilgi.get("hata") or f"çözücü beklenmedik şekilde kapandı (kod {surec.returncode})"
        raise OkumaHatasi(f"{ad}: {mesaj}.")
    return surec.stdout, float(bilgi.get("sure_sn", len(surec.stdout) / 2 / ORNEKLEME))


def wav_yap(pcm: bytes) -> bytes:
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ORNEKLEME)
        w.writeframes(pcm)
    return tampon.getvalue()


_MODELLER: dict = {}


def yerel_yazi_dok(pcm: bytes, model_adi: str) -> str:
    """faster-whisper ile bilgisayarda yazıya döker; ses dışarı çıkmaz."""
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as hata:
        raise OkumaHatasi("Yerel konuşma tanıma için faster-whisper kurulu değil: pip install -r requirements.txt") from hata

    model = _MODELLER.get(model_adi)
    if model is None:
        log.info("Konuşma tanıma modeli (%s) yükleniyor. İlk kullanımda bir kez indirilir (small ≈ 500 MB)...", model_adi)
        try:
            model = WhisperModel(model_adi, device="cpu", compute_type="int8",
                                 download_root=os.environ.get("WHISPER_KLASORU") or None)
        except Exception as hata:
            raise OkumaHatasi(
                f"Konuşma tanıma modeli yüklenemedi ({type(hata).__name__}). İlk kullanımda internet bağlantısı "
                "gerekir; model Hugging Face'ten indirilir."
            ) from hata
        _MODELLER[model_adi] = model

    ses = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    toplam = len(ses) / ORNEKLEME
    # vad_filter: sessiz bölümleri atlar (hem hız hem uydurma satırları azaltır).
    # condition_on_previous_text=False: modelin kendi tekrarına kapılıp döngüye girmesini önler.
    segmentler, _ = model.transcribe(ses, language="tr", vad_filter=True, beam_size=5,
                                     condition_on_previous_text=False)
    satirlar, son_bildirim = [], 0.0
    for seg in segmentler:
        metin = seg.text.strip()
        if metin:
            satirlar.append(f"[{zaman(seg.start)}] {metin}")
        if seg.end - son_bildirim >= 60:
            log.info("Yazıya dökülüyor: %s / %s", zaman(seg.end), zaman(toplam))
            son_bildirim = seg.end
    return "\n".join(satirlar)


def _uydurmalari_ayikla(metin: str, notlar: list[str]) -> str:
    satirlar, atilan = [], 0
    for satir in metin.splitlines():
        govde = satir.split("] ", 1)[-1].strip().lower()
        if govde in UYDURMA_SATIRLAR:
            atilan += 1
            continue
        satirlar.append(satir)
    if atilan:
        notlar.append(f"Konuşma tanımanın uydurduğu bilinen {atilan} satır (ör. 'Altyazı M.K.') atıldı.")
    return "\n".join(satirlar)


def medya_oku(veri: bytes, ad: str, uzanti: str, ayar: OcrAyari) -> OkumaSonucu:
    video = uzanti in VIDEO_UZANTILARI
    tur = _imza_turu(veri)
    if tur not in BEKLENEN_IMZA[uzanti]:
        raise OkumaHatasi(f"{ad}: dosyanın içeriği uzantısıyla uyuşmuyor; bozuk olabilir ya da türü gizlenmiş olabilir.")

    pcm, sure = sesi_coz(veri, ad, ayar.en_uzun_ses_sn)
    if sure < 0.5:
        raise OkumaHatasi(f"{ad}: kayıtta neredeyse hiç ses yok.")
    notlar = [f"{'Video' if video else 'Ses'} kaydı: {zaman(sure)}."]
    if video:
        notlar.append("Videonun yalnızca ses kanalı yazıya döküldü; görüntüdeki yazı ve slaytlar okunmadı.")

    gonderilen = 0
    if ayar.ses_kipi == "gemini":
        if ayar.ses_okuyucu is None:
            raise OkumaHatasi("Model ile ses okuma seçildi ama LLM istemcisi verilmedi.")
        adim = GEMINI_PARCA_SN * ORNEKLEME * 2
        parcalar = [pcm[i:i + adim] for i in range(0, len(pcm), adim)]
        if ayar.on_kontrol:
            ayar.on_kontrol(len(parcalar))  # her parça bir API isteği
        metinler = []
        for sira, parca in enumerate(parcalar):
            log.info("Ses parçası %d/%d sağlayıcıya gönderiliyor...", sira + 1, len(parcalar))
            metin = ayar.ses_okuyucu(wav_yap(parca)).strip()
            if metin:
                metinler.append(f"[{zaman(sira * GEMINI_PARCA_SN)}] {metin}")
            gonderilen += 1
        metin = "\n".join(metinler)
        notlar.append(f"Konuşma model ile yazıya döküldü; ses {gonderilen} parça halinde sağlayıcıya gönderildi.")
    else:
        yazici: Callable[[bytes, str], str] = ayar.transkriptor or yerel_yazi_dok
        metin = yazici(pcm, ayar.whisper_modeli)
        notlar.append(f"Konuşma yerel olarak yazıya döküldü (Whisper {ayar.whisper_modeli}); ses bilgisayardan çıkmadı.")

    metin = metni_temizle(_uydurmalari_ayikla(metin, notlar), notlar)
    if not metin:
        raise OkumaHatasi(f"{ad}: kayıtta anlaşılır bir konuşma bulunamadı.")
    sonuc = OkumaSonucu(metin, "video" if video else "ses", notlar)
    sonuc.ses_suresi_sn = round(sure, 1)
    sonuc.disari_gonderilen_ses_parcasi = gonderilen
    return sonuc
