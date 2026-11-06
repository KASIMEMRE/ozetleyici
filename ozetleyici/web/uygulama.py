"""FastAPI uygulaması: belge yükle, akış halinde özet al.

Güvenlik kararları (her biri bir saldırıya karşı):
- Yalnızca 127.0.0.1'de dinler; kimlik doğrulama olmadığı için ağa açılmaz.
- Host başlığı denetlenir: DNS rebinding ile başka bir sitenin bu sunucuya
  "localhost gibi" erişmesini engeller.
- Her açılışta rastgele bir oturum anahtarı üretilir ve her API isteğinde
  özel bir başlıkta istenir: başka bir sitenin tarayıcın üzerinden istek
  atmasını (CSRF) engeller; özel başlık CORS ön kontrolü gerektirir, biz de
  CORS'a izin vermiyoruz.
- Sıkı Content-Security-Policy: sayfada yalnızca bizim betiğimiz çalışır.
- Yüklenen dosya diske yazılmaz, yalnızca bellekte işlenir; boyutu sınırlıdır.
- Aynı anda tek iş: API kotan ve bütçen kontrolsüz harcanmaz.
"""

from __future__ import annotations

import json
import logging
import queue
import secrets
import threading
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..ayarlar import AyarHatasi, Ayarlar, anahtari_gizle, ayarlari_yukle
from ..cikti import sonuc_sozlugu
from ..gizlilik import kisisel_veri_ipuclari
from ..llm import LLMHatasi, LLMIstemcisi, UretimAyarlari
from ..okuyucular import DESTEKLENEN_UZANTILAR, OcrAyari, OkumaHatasi, belgeyi_oku, tesseract_yolu
from ..ozetle import UZUNLUKLAR, ozetle

log = logging.getLogger(__name__)

STATIK = Path(__file__).parent / "statik"
EN_BUYUK_YUKLEME = 25 * 1024 * 1024  # 25 MB
IZINLI_HOSTLAR = ["127.0.0.1", "localhost"]
OTURUM_BASLIGI = "X-Oturum-Anahtari"

GUVENLIK_BASLIKLARI = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class _IsGunlugu(logging.Handler):
    """Bir işin çalıştığı iş parçacığındaki log kayıtlarını tarayıcıya olay olarak iletir."""

    def __init__(self, is_parcacigi: int, gonder: Callable[[dict], None]) -> None:
        super().__init__(logging.INFO)
        self.is_parcacigi = is_parcacigi
        self.gonder = gonder

    def emit(self, kayit: logging.LogRecord) -> None:
        if kayit.thread == self.is_parcacigi:
            tip = "uyari" if kayit.levelno >= logging.WARNING else "bilgi"
            self.gonder({"tip": tip, "mesaj": kayit.getMessage()})


def uygulama_olustur(
    ayar_yukleyici: Callable[[], Ayarlar] = ayarlari_yukle,
    istemci_fabrikasi: Callable[[Ayarlar], LLMIstemcisi] = LLMIstemcisi,
    oturum_anahtari: str | None = None,
) -> FastAPI:
    anahtar_oturum = oturum_anahtari or secrets.token_urlsafe(32)
    is_kilidi = threading.Lock()

    # docs/openapi kapalı: yerel bir araç için gereksiz saldırı yüzeyi.
    app = FastAPI(title="Belge Özetleyici", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=IZINLI_HOSTLAR)

    @app.middleware("http")
    async def guvenlik_basliklari(request: Request, call_next):
        cevap = await call_next(request)
        for ad, deger in GUVENLIK_BASLIKLARI.items():
            cevap.headers.setdefault(ad, deger)
        if request.url.path.startswith("/api/") or request.url.path == "/":
            cevap.headers["Cache-Control"] = "no-store"
        return cevap

    def oturumu_dogrula(request: Request) -> None:
        gelen = request.headers.get(OTURUM_BASLIGI, "")
        # compare_digest: karşılaştırma süresinden anahtarı tahmin etmeyi (timing attack) engeller
        if not secrets.compare_digest(gelen, anahtar_oturum):
            raise HTTPException(status_code=403, detail="Oturum anahtarı geçersiz. Sayfayı yenile.")

    @app.get("/", response_class=HTMLResponse)
    def ana_sayfa() -> HTMLResponse:
        sayfa = (STATIK / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(sayfa.replace("{{OTURUM_ANAHTARI}}", anahtar_oturum).replace("{{SURUM}}", __version__))

    app.mount("/statik", StaticFiles(directory=STATIK), name="statik")

    @app.get("/api/durum")
    def durum(request: Request) -> dict:
        oturumu_dogrula(request)
        try:
            ayarlar = ayar_yukleyici()
            model, ayar_hatasi = ayarlar.model, None
        except AyarHatasi as hata:
            model, ayar_hatasi = None, str(hata)
        return {
            "surum": __version__,
            "model": model,
            "ayar_hatasi": ayar_hatasi,
            "tesseract": tesseract_yolu() is not None,
            "desteklenen": sorted(DESTEKLENEN_UZANTILAR),
            "en_buyuk_mb": EN_BUYUK_YUKLEME // (1024 * 1024),
            "uzunluklar": list(UZUNLUKLAR),
            "mesgul": is_kilidi.locked(),
        }

    @app.post("/api/ozetle")
    async def ozetle_api(request: Request, ad: str = "", uzunluk: str = "orta", ocr: str = "yerel",
                         yine_de_gonder: bool = False) -> StreamingResponse:
        oturumu_dogrula(request)
        dosya_adi = Path(unquote(ad)).name[:200]  # yol parçalarını at; yalnızca dosya adı
        if not dosya_adi:
            raise HTTPException(400, "Dosya adı eksik.")
        if uzunluk not in UZUNLUKLAR:
            raise HTTPException(400, "Geçersiz uzunluk.")
        if ocr not in ("yerel", "gemini", "kapali"):
            raise HTTPException(400, "Geçersiz OCR seçeneği.")

        bildirilen = request.headers.get("content-length")
        if bildirilen and bildirilen.isdigit() and int(bildirilen) > EN_BUYUK_YUKLEME:
            raise HTTPException(413, f"Dosya çok büyük (sınır {EN_BUYUK_YUKLEME // (1024 * 1024)} MB).")
        # Gövdeyi parça parça oku; sınırı aşarsa hemen kes (Content-Length yalan söyleyebilir).
        parcalar, toplam = [], 0
        async for parca in request.stream():
            toplam += len(parca)
            if toplam > EN_BUYUK_YUKLEME:
                raise HTTPException(413, f"Dosya çok büyük (sınır {EN_BUYUK_YUKLEME // (1024 * 1024)} MB).")
            parcalar.append(parca)
        veri = b"".join(parcalar)
        del parcalar
        if not veri:
            raise HTTPException(400, "Dosya boş.")

        if not is_kilidi.acquire(blocking=False):
            raise HTTPException(429, "Başka bir belge işleniyor; bitmesini bekle.")

        olaylar: queue.Queue = queue.Queue()
        BITTI = object()

        def gonder(olay: dict) -> None:
            olaylar.put(olay)

        def is_() -> None:
            # Kilidi işi yapan iş parçacığı bırakır: tarayıcı sekmesi kapansa bile
            # iş bitene kadar ikinci bir iş başlamaz.
            gunluk = _IsGunlugu(threading.get_ident(), gonder)
            kok = logging.getLogger("ozetleyici")
            kok.addHandler(gunluk)
            onceki_seviye = kok.level
            if kok.level == logging.NOTSET or kok.level > logging.INFO:
                kok.setLevel(logging.INFO)
            try:
                _isle(veri, dosya_adi, uzunluk, ocr, yine_de_gonder, gonder,
                                ayar_yukleyici, istemci_fabrikasi)
            except (OkumaHatasi, AyarHatasi, LLMHatasi, ValueError) as hata:
                # LLMHatasi mesajlarındaki anahtar istemci tarafından zaten gizlendi.
                gonder({"tip": "hata", "mesaj": str(hata)})
            except Exception:  # beklenmeyen hata: ayrıntı sunucu günlüğüne, tarayıcıya genel mesaj
                log.exception("Beklenmeyen hata (%s)", dosya_adi)
                gonder({"tip": "hata", "mesaj": "Beklenmeyen bir hata oluştu. Ayrıntı terminalde."})
            finally:
                kok.removeHandler(gunluk)
                kok.setLevel(onceki_seviye)
                is_kilidi.release()
                olaylar.put(BITTI)

        threading.Thread(target=is_, name=f"ozet-{dosya_adi}", daemon=True).start()

        def akis() -> Iterator[bytes]:
            while True:
                olay = olaylar.get()
                if olay is BITTI:
                    return
                yield (json.dumps(olay, ensure_ascii=False) + "\n").encode("utf-8")

        return StreamingResponse(akis(), media_type="application/x-ndjson")

    @app.exception_handler(HTTPException)
    async def http_hatasi(request: Request, hata: HTTPException) -> JSONResponse:
        return JSONResponse({"hata": hata.detail}, status_code=hata.status_code)

    return app


def _isle(veri: bytes, ad: str, uzunluk: str, ocr_kipi: str, yine_de_gonder: bool,
          gonder: Callable[[dict], None], ayar_yukleyici, istemci_fabrikasi) -> None:
    gonder({"tip": "bilgi", "mesaj": f"{ad} okunuyor..."})
    istemci = None
    ayarlar = None

    def istemci_al():
        nonlocal istemci, ayarlar
        if istemci is None:
            ayarlar = ayar_yukleyici()
            istemci = istemci_fabrikasi(ayarlar)
        return istemci

    ocr = OcrAyari(kip=ocr_kipi)
    if ocr_kipi == "gemini":
        ocr = OcrAyari(kip="gemini", gorsel_okuyucu=lambda png: istemci_al().gorseli_metne_cevir(png))

    okuma = belgeyi_oku(veri, ad, ocr)
    for not_ in okuma.notlar:
        gonder({"tip": "not", "mesaj": not_})

    bulgular = kisisel_veri_ipuclari(okuma.metin)
    if bulgular and not yine_de_gonder:
        gonder({"tip": "kisisel_veri", "bulgular": bulgular})
        return

    istemci_al()
    gonder({"tip": "bilgi", "mesaj": f"{len(okuma.metin):,} karakter okundu. Model: {ayarlar.model}".replace(",", ".")})
    sonuc = ozetle(
        okuma.metin, istemci, UretimAyarlari(), uzunluk=uzunluk,
        girdi_fiyati=ayarlar.girdi_fiyati, cikti_fiyati=ayarlar.cikti_fiyati,
        parca_gelince=lambda p: gonder({"tip": "parca", "metin": p}),
        akis_sifirlandi=lambda: gonder({"tip": "sifirla"}),
    )
    ek = {
        "belge_turu": okuma.tur,
        "okuma_notlari": okuma.notlar,
        "ocr_sayfa_sayisi": okuma.ocr_sayfa_sayisi,
        "saglayiciya_gonderilen_gorsel": okuma.disari_gonderilen_gorsel,
        "ocr_girdi_token": getattr(istemci, "ocr_girdi_token", 0),
        "ocr_cikti_token": getattr(istemci, "ocr_cikti_token", 0),
    }
    sozluk = sonuc_sozlugu(sonuc, ad, ek)
    gonder({"tip": "bitti", "sonuc": json.loads(anahtari_gizle(json.dumps(sozluk, ensure_ascii=False), ayarlar.api_anahtari))})
