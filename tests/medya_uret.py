"""Test için ses/video dosyalarını PyAV ile üretir (ffmpeg programı gerekmez)."""

import io
import math

import av
import numpy as np

ORNEK = 16_000


def sinus(saniye: float, frekans: float = 440.0, oran: int = ORNEK) -> np.ndarray:
    t = np.arange(int(saniye * oran)) / oran
    return (0.3 * np.sin(2 * math.pi * frekans * t) * 32767).astype("<i2")


def ses_dosyasi(bicim: str, kodek: str, saniye: float = 3.0, oran: int = 48_000) -> bytes:
    tampon = io.BytesIO()
    kap = av.open(tampon, mode="w", format=bicim)
    akis = kap.add_stream(kodek, rate=oran)
    akis.layout = "mono"
    ornekler = sinus(saniye, oran=oran)
    kare_boyu = akis.codec_context.frame_size or 1024
    for i in range(0, len(ornekler), kare_boyu):
        parca = ornekler[i:i + kare_boyu]
        kare = av.AudioFrame.from_ndarray(parca.reshape(1, -1), format="s16", layout="mono")
        kare.sample_rate = oran
        for p in akis.encode(kare):
            kap.mux(p)
    for p in akis.encode(None):
        kap.mux(p)
    kap.close()
    return tampon.getvalue()


def video_dosyasi(bicim: str, video_kodek: str, ses_kodek: str | None, saniye: float = 2.0) -> bytes:
    tampon = io.BytesIO()
    kap = av.open(tampon, mode="w", format=bicim)
    v = kap.add_stream(video_kodek, rate=10)
    v.width, v.height, v.pix_fmt = 64, 48, "yuv420p"
    a = None
    if ses_kodek:
        a = kap.add_stream(ses_kodek, rate=48_000)
        a.layout = "mono"
    for i in range(int(saniye * 10)):
        resim = np.full((48, 64, 3), (i * 10) % 255, dtype=np.uint8)
        for p in v.encode(av.VideoFrame.from_ndarray(resim, format="rgb24").reformat(format="yuv420p")):
            kap.mux(p)
    for p in v.encode(None):
        kap.mux(p)
    if a is not None:
        ornekler = sinus(saniye, oran=48_000)
        boy = a.codec_context.frame_size or 1024
        for i in range(0, len(ornekler), boy):
            kare = av.AudioFrame.from_ndarray(ornekler[i:i + boy].reshape(1, -1), format="s16", layout="mono")
            kare.sample_rate = 48_000
            for p in a.encode(kare):
                kap.mux(p)
        for p in a.encode(None):
            kap.mux(p)
    kap.close()
    return tampon.getvalue()
