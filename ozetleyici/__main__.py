"""Komut satırı girişi:  python -m ozetleyici belge.pdf"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .ayarlar import AyarHatasi, ayarlari_yukle
from .cikti import json_yaz
from .llm import LLMHatasi, LLMIstemcisi, UretimAyarlari
from .okuyucu import OkumaHatasi, metni_oku
from .ozetle import UZUNLUKLAR, ozetle


def arguman_ayristirici() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ozetleyici",
        description="PDF veya metin dosyasını LLM ile özetleyip JSON olarak kaydeder.",
    )
    p.add_argument("dosya", type=Path, help="Özetlenecek .pdf, .txt veya .md dosyası")
    p.add_argument("-o", "--cikti", type=Path, help="JSON çıktı yolu (varsayılan: <dosya>.ozet.json)")
    p.add_argument("-u", "--uzunluk", choices=list(UZUNLUKLAR), default="orta", help="Özet uzunluğu (varsayılan: orta)")
    p.add_argument("--model", help="Model adını .env'dekinin yerine bu çalıştırma için değiştir")
    p.add_argument("--temperature", type=float, help="Rastgelelik, 0-1 arası (verilmezse gönderilmez)")
    p.add_argument("--top-p", type=float, help="Çekirdek örnekleme, 0-1 arası (verilmezse gönderilmez)")
    p.add_argument("--max-token", type=int, default=1024, help="Cevapta en fazla token (varsayılan: 1024)")
    p.add_argument("--akissiz", action="store_true", help="Cevabı akış halinde değil, tek seferde al")
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows terminalinde Türkçe karakterler bozulmasın.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = arguman_ayristirici().parse_args(argv)
    hedef = args.cikti or args.dosya.with_suffix(".ozet.json")

    try:
        metin = metni_oku(args.dosya)
        ayarlar = ayarlari_yukle()
        if args.model:
            ayarlar = replace(ayarlar, model=args.model)
        istemci = LLMIstemcisi(ayarlar)
        uretim = UretimAyarlari(temperature=args.temperature, top_p=args.top_p, max_token=args.max_token)

        print(f"[bilgi] {args.dosya.name}: {len(metin):,} karakter okundu. Model: {ayarlar.model}\n")
        yazdir = None if args.akissiz else (lambda p: print(p, end="", flush=True))
        sonuc = ozetle(
            metin, istemci, uretim, uzunluk=args.uzunluk,
            girdi_fiyati=ayarlar.girdi_fiyati, cikti_fiyati=ayarlar.cikti_fiyati,
            parca_gelince=yazdir,
        )
        if args.akissiz:
            print(sonuc.ozet)
        json_yaz(sonuc, args.dosya, hedef)
    except (OkumaHatasi, AyarHatasi, LLMHatasi, ValueError) as hata:
        print(f"\n[hata] {hata}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[iptal] Kullanıcı durdurdu.", file=sys.stderr)
        return 130

    maliyet = f"${sonuc.maliyet_usd:.6f}" if sonuc.maliyet_usd is not None else "hesaplanmadı (fiyat ayarı yok)"
    token = f"{sonuc.girdi_token} girdi + {sonuc.cikti_token} çıktı" if sonuc.girdi_token is not None else "sağlayıcı bildirmedi"
    print(f"\n\n[bitti] {hedef} kaydedildi | {sonuc.sure_sn} sn | token: {token} | maliyet: {maliyet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
