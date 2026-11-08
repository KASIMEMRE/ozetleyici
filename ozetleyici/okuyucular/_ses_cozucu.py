"""Ayrı süreçte çalışan ses çözücü (yalnızca medya.py tarafından çağrılır).

Neden ayrı süreç? Ses/video çözümleyicileri (ffmpeg) güvenilmeyen dosyaları
ayrıştırır ve geçmişte çok sayıda güvenlik açığı çıkmıştır. Ayrı süreçte
çalıştırınca bir çökme ana programı düşürmez, süre ve bellek sınırlanabilir,
API anahtarları da bu sürecin ortamına hiç verilmez.

Girdi : stdin'den dosyanın baytları
        argv[1] = en uzun süre (saniye), argv[2] = bellek sınırı (bayt), argv[3] = işlemci süresi sınırı (saniye)
Çıktı : stdout'a 16 kHz, mono, 16 bit ham ses (PCM)
        stderr'e tek satır JSON: {"sure_sn": ...} veya {"hata": "...", "kod": ...}
"""

import io
import json
import sys

ORNEKLEME = 16_000


def bildir(veri: dict) -> None:
    # Yalnızca ASCII JSON yaz: Windows'ta yönlendirilmiş çıktının kodlaması UTF-8 değil
    # (cp1254) olabilir; "ı" gibi harfler \u0131 olarak kaçışlanınca hiç bozulmaz.
    sys.stderr.buffer.write((json.dumps(veri, ensure_ascii=True) + "\n").encode("ascii"))
    sys.stderr.buffer.flush()


def bitir(hata: str, kod: int) -> None:
    bildir({"hata": hata, "kod": kod})
    sys.exit(kod)


def sinirlari_uygula(bellek: int, islemci_sn: int) -> None:
    """Linux/macOS'ta bu sürecin kaynaklarını sınırla (Windows'ta 'resource' modülü yok).

    Sınırlar ana programdan preexec_fn ile değil, burada konur: preexec_fn çok iş
    parçacıklı programlarda (web sunucusu gibi) kilitlenmeye yol açabilir.
    """
    try:
        import resource
    except ImportError:
        return
    resource.setrlimit(resource.RLIMIT_AS, (bellek, bellek))
    resource.setrlimit(resource.RLIMIT_CPU, (islemci_sn, islemci_sn))


def main() -> None:
    en_uzun_sn = float(sys.argv[1])
    if len(sys.argv) >= 4:
        sinirlari_uygula(int(sys.argv[2]), int(sys.argv[3]))
    veri = sys.stdin.buffer.read()
    try:
        import av
    except ImportError:
        bitir("PyAV kurulu değil (pip install -r requirements.txt).", 5)
    try:
        kap = av.open(io.BytesIO(veri), mode="r")
    except Exception as hata:
        bitir(f"dosya çözülemedi ({type(hata).__name__}); bozuk ya da desteklenmeyen bir biçim olabilir", 4)

    sesler = [s for s in kap.streams if s.type == "audio"]
    if not sesler:
        bitir("dosyada ses kanalı yok", 2)
    bildirilen = kap.duration / 1_000_000 if kap.duration else None  # mikrosaniye
    if bildirilen and bildirilen > en_uzun_sn:
        bitir(f"kayıt çok uzun: {bildirilen / 60:.0f} dakika (sınır {en_uzun_sn / 60:.0f} dakika)", 3)

    donusturucu = av.AudioResampler(format="s16", layout="mono", rate=ORNEKLEME)
    sinir_bayt = int(en_uzun_sn * ORNEKLEME * 2)
    yazilan = 0
    cikis = sys.stdout.buffer

    def yaz(kareler) -> None:
        nonlocal yazilan
        for kare in kareler:
            parca = kare.to_ndarray().astype("<i2").tobytes()
            yazilan += len(parca)
            # Dosyanın bildirdiği süre yalan olabilir: gerçekte çözülen miktara bakıyoruz.
            if yazilan > sinir_bayt:
                bitir(f"kayıt {en_uzun_sn / 60:.0f} dakikadan uzun", 3)
            cikis.write(parca)

    try:
        for paket in kap.demux(sesler[0]):
            for kare in paket.decode():
                yaz(donusturucu.resample(kare))
        yaz(donusturucu.resample(None))  # tampondaki son örnekler
    except av.FFmpegError as hata:
        if yazilan == 0:
            bitir(f"ses çözülemedi ({type(hata).__name__})", 4)
        # Dosyanın sonu bozuksa o ana kadar çözüleni kullan
    cikis.flush()
    bildir({"sure_sn": round(yazilan / 2 / ORNEKLEME, 2)})


if __name__ == "__main__":
    main()
