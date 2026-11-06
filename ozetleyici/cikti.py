"""Özet sonucunu JSON dosyasına yazar."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .ozetle import OzetSonucu


def sonuc_sozlugu(sonuc: OzetSonucu, kaynak_adi: str, ek: dict | None = None) -> dict:
    """JSON'a yazılacak sözlüğü üretir (web uygulaması da bunu kullanır)."""
    # Bilerek YAZMADIKLARIMIZ: API anahtarı, belgenin tam metni, kaynağın tam yolu
    # (kullanıcı adını içerebilir). Yalnızca dosya adı yazılır.
    veri = {
        "kaynak_dosya": kaynak_adi,
        "olusturulma": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arac_surumu": __version__,
        **asdict(sonuc),
        **(ek or {}),
    }
    return veri


def json_yaz(sonuc: OzetSonucu, kaynak: Path, hedef: Path, ek: dict | None = None) -> dict:
    veri = sonuc_sozlugu(sonuc, kaynak.name, ek)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False olmazsa "ş" dosyaya "ş" diye yazılır.
    hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return veri
