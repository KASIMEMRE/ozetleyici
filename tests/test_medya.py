"""Ses ve video okuma testleri: gerçek dosyalar, ayrı süreçte gerçek çözme.

Konuşma tanıma modeli (Whisper) testlerde yerine sahte bir fonksiyonla geçer; modelin
kendisi tests/test_gercek_api.py içinde, isteğe bağlı olarak denenir.
"""

import io
import wave

import pytest

from ozetleyici.okuyucular import OcrAyari, OkumaHatasi, belgeyi_oku, medya
from tests.medya_uret import ses_dosyasi, video_dosyasi


def yaziya_dokucu(kayit: list):
    def dok(pcm: bytes, model: str) -> str:
        kayit.append((len(pcm), model))
        return f"[00:00] Toplantıda bütçe onaylandı ({len(pcm) // 32000} sn)."
    return dok


@pytest.mark.parametrize("ad,bicim,kodek", [
    ("kayit.wav", "wav", "pcm_s16le"),
    ("kayit.mp3", "mp3", "libmp3lame"),
    ("kayit.m4a", "ipod", "aac"),
    ("kayit.ogg", "ogg", "libopus"),
    ("kayit.flac", "flac", "flac"),
])
def test_ses_bicimleri_cozulur_ve_yaziya_dokulur(ad, bicim, kodek):
    kayit = []
    sonuc = belgeyi_oku(ses_dosyasi(bicim, kodek, saniye=3), ad, OcrAyari(transkriptor=yaziya_dokucu(kayit)))
    assert sonuc.tur == "ses" and 2.8 <= sonuc.ses_suresi_sn <= 3.3
    assert "bütçe onaylandı" in sonuc.metin
    pcm_boyu, model = kayit[0]
    assert 2.8 * 32000 <= pcm_boyu <= 3.3 * 32000 and model == "small"  # 16 kHz mono 16 bit
    assert any("ses bilgisayardan çıkmadı" in n for n in sonuc.notlar)


@pytest.mark.parametrize("ad,bicim,vk,sk", [
    ("toplanti.mp4", "mp4", "mpeg4", "aac"),
    ("toplanti.mov", "mov", "mpeg4", "aac"),
    ("toplanti.webm", "webm", "libvpx", "libopus"),
    ("toplanti.mkv", "matroska", "mpeg4", "aac"),
])
def test_videonun_ses_kanali_okunur(ad, bicim, vk, sk):
    sonuc = belgeyi_oku(video_dosyasi(bicim, vk, sk, saniye=2), ad, OcrAyari(transkriptor=yaziya_dokucu([])))
    assert sonuc.tur == "video" and 1.8 <= sonuc.ses_suresi_sn <= 2.3
    assert any("görüntüdeki yazı ve slaytlar okunmadı" in n for n in sonuc.notlar)


def test_sessiz_video_anlamli_hata():
    with pytest.raises(OkumaHatasi, match="ses kanalı yok"):
        belgeyi_oku(video_dosyasi("mp4", "mpeg4", None), "sessiz.mp4", OcrAyari(transkriptor=yaziya_dokucu([])))


def test_cok_uzun_kayit_reddedilir():
    with pytest.raises(OkumaHatasi, match="çok uzun|dakikadan uzun"):
        belgeyi_oku(ses_dosyasi("wav", "pcm_s16le", saniye=5), "uzun.wav",
                    OcrAyari(transkriptor=yaziya_dokucu([]), en_uzun_ses_sn=2))


def test_suresini_gizleyen_dosya_cozulurken_kesilir():
    """Başlığında süre yazmayan (ham) bir akış: sınır gerçekten çözülen miktara göre uygulanır."""
    ham = ses_dosyasi("adts", "aac", saniye=5)  # ADTS: süre başlıkta yok
    veri = ham
    # .m4a değil; ADTS'yi mp3 kılığında gönderemeyiz (imza tutmaz). Doğrudan çözücüyü sınayalım:
    with pytest.raises(OkumaHatasi, match="dakikadan uzun|çok uzun"):
        medya.sesi_coz(veri, "akis.aac", en_uzun_sn=2)


def test_kilik_degistirmis_medya_reddedilir():
    mp3 = ses_dosyasi("mp3", "libmp3lame")
    with pytest.raises(OkumaHatasi, match="uyuşmuyor"):
        belgeyi_oku(mp3, "aslinda_mp3.wav", OcrAyari(transkriptor=yaziya_dokucu([])))
    with pytest.raises(OkumaHatasi, match="uyuşmuyor"):
        belgeyi_oku(b"%PDF-1.4 sahte", "belge.mp4", OcrAyari(transkriptor=yaziya_dokucu([])))


def test_bozuk_medya_anlamli_hata_ve_ana_program_cokmez():
    bozuk = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(range(256)) * 20
    with pytest.raises(OkumaHatasi):
        belgeyi_oku(bozuk, "bozuk.wav", OcrAyari(transkriptor=yaziya_dokucu([])))


def test_cozucu_surec_api_anahtarini_gormez(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "gizli-anahtar-123")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_gizli")
    monkeypatch.setenv("NORMAL_DEGISKEN", "kalsin")
    gorulen = {}
    gercek = medya.subprocess.run

    def yakala(*a, **k):
        gorulen.update(k["env"])
        return gercek(*a, **k)

    monkeypatch.setattr(medya.subprocess, "run", yakala)
    medya.sesi_coz(ses_dosyasi("wav", "pcm_s16le", saniye=1), "a.wav", 60)
    assert "LLM_API_KEY" not in gorulen and "GITHUB_TOKEN" not in gorulen
    assert gorulen.get("NORMAL_DEGISKEN") == "kalsin"


def test_gemini_ses_parcalara_bolunur_ve_butce_once_sorulur(monkeypatch):
    monkeypatch.setattr(medya, "GEMINI_PARCA_SN", 2)
    gelen, kontrol = [], []

    def okuyucu(wav: bytes) -> str:
        with wave.open(io.BytesIO(wav)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
            gelen.append(w.getnframes() / 16000)
        return "Konuşmacı 1: Merhaba"

    ayar = OcrAyari(ses_kipi="gemini", ses_okuyucu=okuyucu, on_kontrol=kontrol.append)
    sonuc = belgeyi_oku(ses_dosyasi("wav", "pcm_s16le", saniye=5), "a.wav", ayar)
    assert kontrol == [3] and len(gelen) == 3  # 2 + 2 + 1 sn
    assert sonuc.disari_gonderilen_ses_parcasi == 3
    assert "[00:00] Konuşmacı 1" in sonuc.metin and "[00:04]" in sonuc.metin
    assert any("sağlayıcıya gönderildi" in n for n in sonuc.notlar)


def test_gemini_ses_butce_asilirsa_hic_gonderilmez(monkeypatch):
    from ozetleyici.llm import ButceAsildi, IstekButcesi
    monkeypatch.setattr(medya, "GEMINI_PARCA_SN", 1)
    gonderilen = []
    ayar = OcrAyari(ses_kipi="gemini", ses_okuyucu=lambda w: gonderilen.append(1) or "x",
                    on_kontrol=IstekButcesi(2).on_kontrol)
    with pytest.raises(ButceAsildi):
        belgeyi_oku(ses_dosyasi("wav", "pcm_s16le", saniye=5), "a.wav", ayar)
    assert gonderilen == []


def test_whisper_uydurmalari_ayiklanir():
    def dok(pcm, model):
        return "[00:00] Gündem maddesi kabul edildi.\n[00:05] Altyazı M.K.\n[00:09] Toplantı bitti."
    sonuc = belgeyi_oku(ses_dosyasi("wav", "pcm_s16le", saniye=2), "a.wav", OcrAyari(transkriptor=dok))
    assert "Altyazı" not in sonuc.metin and "Toplantı bitti" in sonuc.metin
    assert any("uydurduğu" in n for n in sonuc.notlar)


def test_konusma_yoksa_anlamli_hata():
    with pytest.raises(OkumaHatasi, match="anlaşılır bir konuşma"):
        belgeyi_oku(ses_dosyasi("wav", "pcm_s16le", saniye=2), "a.wav", OcrAyari(transkriptor=lambda p, m: ""))


def test_whisper_kurulu_degilse_anlamli_hata(monkeypatch):
    import builtins
    gercek_import = builtins.__import__

    def engelle(ad, *a, **k):
        if ad == "faster_whisper":
            raise ImportError("yok")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", engelle)
    with pytest.raises(OkumaHatasi, match="faster-whisper kurulu değil"):
        medya.yerel_yazi_dok(b"\0\0" * 16000, "small")



def test_cozucu_bellek_siniri_uygulanir(monkeypatch):
    """Linux/macOS'ta çözücü süreç bellek sınırını aşınca çöker; ana program anlamlı hata verir."""
    import os
    if os.name != "posix":
        pytest.skip("bellek sınırı yalnızca Linux/macOS'ta")
    monkeypatch.setattr(medya, "COZUCU_BELLEK_SINIRI", 50 * 1024 * 1024)  # 50 MB: Python + PyAV'a yetmez
    with pytest.raises(OkumaHatasi):
        medya.sesi_coz(ses_dosyasi("wav", "pcm_s16le", saniye=1), "a.wav", 60)


def test_cok_is_parcacikli_programda_kilitlenmez():
    """Web sunucusu gibi çok iş parçacıklı bir ortamda çözücü sürecini başlatmak donmamalı.

    Risk fork() kaynaklıdır (preexec_fn); Windows fork kullanmadığı için orada geçerli değil.
    """
    import os
    if os.name != "posix":
        pytest.skip("fork kilitlenmesi yalnızca Linux/macOS'ta mümkün")
    import threading
    import time
    dur = threading.Event()

    def mesgul():  # başka iş parçacıkları sürekli modül içe aktarıp kilit tutsun
        while not dur.is_set():
            __import__("json"); __import__("wave")

    isler = [threading.Thread(target=mesgul, daemon=True) for _ in range(8)]
    for i in isler:
        i.start()
    try:
        basla = time.monotonic()
        for _ in range(5):
            medya.sesi_coz(ses_dosyasi("wav", "pcm_s16le", saniye=1), "a.wav", 60)
        assert time.monotonic() - basla < 60
    finally:
        dur.set()



def test_cozucu_mesajlari_kodlamadan_bagimsiz():
    """Windows'ta yönlendirilmiş çıktı UTF-8 değildir; çözücü yalnızca ASCII yazmalı."""
    import subprocess
    import sys
    surec = subprocess.run([sys.executable, "-I", str(medya.COZUCU), "60"],
                           input=video_dosyasi("mp4", "mpeg4", None), capture_output=True, timeout=120)
    son = surec.stderr.strip().splitlines()[-1]
    son.decode("ascii")  # ASCII değilse UnicodeDecodeError
    import json
    assert json.loads(son)["hata"] == "dosyada ses kanalı yok"
