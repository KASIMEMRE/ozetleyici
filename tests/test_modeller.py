from ozetleyici.modeller import ozet_modelleri

# Kullanıcının anahtarından gelen gerçek liste (2026-11-06)
GERCEK = """gemini-3.1-flash-lite-preview gemini-3.1-flash-live-preview gemini-3.1-flash-tts-preview gemini-3.1-pro-preview
gemini-3.1-pro-preview-customtools gemini-3.5-flash gemini-3.5-flash-lite gemini-3.5-live-translate-preview
gemini-3.5-transcribe gemini-3.5-transcribe-live gemini-3.6-flash gemini-3.7-flash gemini-3.8-flash
gemini-3.8-flash-lite-tts gemini-3.8-flash-tts gemini-3.8-live gemini-3.8-live-extended-thinking gemini-4-argon
gemini-embedding-001 gemini-embedding-2 gemini-embedding-2-preview gemini-flash-latest gemini-flash-lite-latest
gemini-nano-banana-2.1 gemini-omni-1.1-flash gemini-omni-flash-preview gemini-pro-latest gemini-robotics-er-2-preview
gemini-robotics-er-2-streaming-preview gemma-4-26b-a4b-it gemma-4-31b-it lyria-3-clip-preview lyria-3-pro-preview
lyria-3.5 lyria-realtime-exp nano-banana-pro-preview""".split()


def test_gercek_listeden_ozet_modelleri():
    sonuc = ozet_modelleri(GERCEK, "gemini-3.5-flash-lite")
    assert sonuc[0] == "gemini-3.5-flash-lite"  # varsayılan başta
    for ad in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-pro-preview", "gemma-4-31b-it", "gemini-flash-latest"):
        assert ad in sonuc
    for ad in ("gemini-embedding-001", "gemini-3.8-flash-tts", "gemini-3.8-live", "lyria-3.5",
               "gemini-nano-banana-2.1", "gemini-3.5-transcribe", "gemini-robotics-er-2-preview", "gemini-omni-1.1-flash"):
        assert ad not in sonuc
    assert len(sonuc) == len(set(sonuc))


def test_hafif_modeller_once_buyukler_sonra():
    sonuc = ozet_modelleri(["gemini-pro-x", "gemini-flash-x", "gemini-flash-lite-x"], "v")
    assert sonuc == ["v", "gemini-flash-lite-x", "gemini-flash-x", "gemini-pro-x"]
