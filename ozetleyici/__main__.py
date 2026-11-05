"""Komut satırı girişi:  python -m ozetleyici belge.pdf"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from .ayarlar import AyarHatasi, anahtari_gizle, ayarlari_yukle
from .cikti import json_yaz
from .gizlilik import kisisel_veri_ipuclari
from .llm import LLMHatasi, LLMIstemcisi, UretimAyarlari
from .okuyucu import OkumaHatasi, metni_oku
from .ozetle import UZUNLUKLAR, ozetle

# Çıkış kodları: başka programlar ve CI bunlara bakar.
BASARILI, HATA, KISISEL_VERI, IPTAL = 0, 1, 3, 130

SEVIYE_ADLARI = {"INFO": "bilgi", "WARNING": "uyarı", "ERROR": "hata", "DEBUG": "ayrıntı"}


class TurkceBicim(logging.Formatter):
    def format(self, kayit: logging.LogRecord) -> str:
        return f"[{SEVIYE_ADLARI.get(kayit.levelname, kayit.levelname)}] {kayit.getMessage()}"


def _aralik(ad: str, en_az: float, en_cok: float, tip=float):
    """argparse için: değerin belirli bir aralıkta olduğunu doğrulayan tür fonksiyonu."""
    def dogrula(metin: str):
        try:
            deger = tip(metin.replace(",", "."))
        except ValueError:
            raise argparse.ArgumentTypeError(f"{ad} bir sayı olmalı: {metin!r}")
        if not en_az <= deger <= en_cok:
            raise argparse.ArgumentTypeError(f"{ad} {en_az} ile {en_cok} arasında olmalı, gelen: {deger}")
        return deger
    return dogrula


def arguman_ayristirici() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ozetleyici",
        description="PDF veya metin dosyasını LLM ile özetleyip JSON olarak kaydeder.",
    )
    p.add_argument("dosya", type=Path, help="Özetlenecek .pdf, .txt veya .md dosyası")
    p.add_argument("-o", "--cikti", type=Path, help="JSON çıktı yolu (varsayılan: <dosya>.ozet.json)")
    p.add_argument("-u", "--uzunluk", choices=list(UZUNLUKLAR), default="orta",
                   help="Özet uzunluğu (varsayılan: orta)")
    p.add_argument("--model", help="Model adını .env'dekinin yerine bu çalıştırma için değiştir")
    p.add_argument("--temperature", type=_aralik("temperature", 0, 2),
                   help="Rastgelelik, 0-2 arası (verilmezse gönderilmez)")
    p.add_argument("--top-p", type=_aralik("top-p", 0.01, 1),
                   help="Çekirdek örnekleme, 0.01-1 arası (verilmezse gönderilmez)")
    p.add_argument("--max-token", type=_aralik("max-token", 16, 65536, int), default=1024,
                   help="Cevapta en fazla token (varsayılan: 1024)")
    p.add_argument("--akissiz", action="store_true", help="Cevabı akış halinde değil, tek seferde al")
    p.add_argument("--yine-de-gonder", action="store_true",
                   help="Belgede kişisel veri ipucu bulunsa bile sağlayıcıya gönder")
    p.add_argument("-s", "--sessiz", action="store_true", help="Bilgi mesajlarını gösterme")
    return p


def _logging_kur(sessiz: bool) -> None:
    isleyici = logging.StreamHandler(sys.stderr)
    isleyici.setFormatter(TurkceBicim())
    kok = logging.getLogger("ozetleyici")
    kok.handlers[:] = [isleyici]
    kok.setLevel(logging.WARNING if sessiz else logging.INFO)
    kok.propagate = False


def main(argv: list[str] | None = None) -> int:
    # Windows terminalinde veya çıktı dosyaya yönlendirildiğinde Türkçe karakterler bozulmasın.
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8")

    args = arguman_ayristirici().parse_args(argv)
    _logging_kur(args.sessiz)
    log = logging.getLogger("ozetleyici")
    hedef = args.cikti or args.dosya.with_suffix(".ozet.json")
    anahtar: str | None = None

    try:
        metin = metni_oku(args.dosya)

        bulgular = kisisel_veri_ipuclari(metin)
        if bulgular and not args.yine_de_gonder:
            ozet = ", ".join(f"{adet} {tur}" for tur, adet in bulgular.items())
            print(
                f"[durdu] Belgede kişisel veri olabilir: {ozet}.\n"
                "        Belge LLM sağlayıcısına gönderilecekti. Ücretsiz katmanlarda gönderilen içerik\n"
                "        model geliştirmede kullanılabilir ve insanlar tarafından okunabilir.\n"
                "        Bilerek göndermek istiyorsan --yine-de-gonder ekle.",
                file=sys.stderr,
            )
            return KISISEL_VERI

        ayarlar = ayarlari_yukle()
        anahtar = ayarlar.api_anahtari
        if args.model:
            ayarlar = replace(ayarlar, model=args.model)
        istemci = LLMIstemcisi(ayarlar)
        uretim = UretimAyarlari(temperature=args.temperature, top_p=args.top_p, max_token=args.max_token)

        log.info("%s: %s karakter okundu. Model: %s", args.dosya.name, f"{len(metin):,}", ayarlar.model)
        print()

        def yazdir(parca: str) -> None:
            print(parca, end="", flush=True)

        def sifirlandi() -> None:
            print("\n", flush=True)
            log.warning("Bağlantı yarıda kesildi; yukarıdaki yarım cevabı yok say, cevap baştan alınıyor:")

        sonuc = ozetle(
            metin, istemci, uretim, uzunluk=args.uzunluk,
            girdi_fiyati=ayarlar.girdi_fiyati, cikti_fiyati=ayarlar.cikti_fiyati,
            parca_gelince=None if args.akissiz else yazdir,
            akis_sifirlandi=None if args.akissiz else sifirlandi,
        )
        if args.akissiz:
            print(sonuc.ozet)
        json_yaz(sonuc, args.dosya, hedef)
    except (OkumaHatasi, AyarHatasi, LLMHatasi, ValueError, OSError) as hata:
        print(f"\n[hata] {anahtari_gizle(str(hata), anahtar)}", file=sys.stderr)
        return HATA
    except KeyboardInterrupt:
        print("\n[iptal] Kullanıcı durdurdu.", file=sys.stderr)
        return IPTAL

    maliyet = f"${sonuc.maliyet_usd:.6f}" if sonuc.maliyet_usd is not None else "hesaplanmadı (fiyat ayarı yok)"
    token = (f"{sonuc.girdi_token} girdi + {sonuc.cikti_token} çıktı"
             if sonuc.girdi_token is not None else "sağlayıcı bildirmedi")
    print(f"\n\n[bitti] {hedef} kaydedildi | {sonuc.sure_sn} sn | token: {token} | maliyet: {maliyet}")
    if len(sonuc.kullanilan_modeller) > 1:
        log.warning("Birden fazla model kullanıldı (%s); maliyet yaklaşık değerdir.",
                    ", ".join(sonuc.kullanilan_modeller))
    return BASARILI


if __name__ == "__main__":
    sys.exit(main())
