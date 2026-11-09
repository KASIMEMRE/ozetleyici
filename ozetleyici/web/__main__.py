"""Web arayüzünü başlatır:  python -m ozetleyici.web"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import webbrowser


class _AnahtarGizleyici(logging.Formatter):
    """Terminale yazılan hata ayrıntısında (traceback dahil) API anahtarı görünmesin."""

    def format(self, kayit: logging.LogRecord) -> str:
        from ..ayarlar import anahtari_gizle

        return anahtari_gizle(super().format(kayit), os.environ.get("LLM_API_KEY"))


def _terminale_hata_yaz() -> None:
    """Uyarı ve hataları (beklenmeyen hatanın traceback'i dahil) terminale yazar."""
    isleyici = logging.StreamHandler(sys.stderr)
    isleyici.setLevel(logging.WARNING)
    isleyici.setFormatter(_AnahtarGizleyici("[%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger("ozetleyici").addHandler(isleyici)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ozetleyici.web", description="Belge özetleyicinin web arayüzü.")
    p.add_argument("--port", type=int, default=8765, help="Port (varsayılan 8765)")
    p.add_argument("--tarayici-acma", action="store_true", help="Tarayıcıyı otomatik açma")
    args = p.parse_args(argv)

    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8")

    import uvicorn
    from dotenv import load_dotenv

    from .uygulama import uygulama_olustur

    load_dotenv()
    _terminale_hata_yaz()
    # Bilerek 127.0.0.1: uygulamada kullanıcı girişi yok. Ağa açılırsa aynı ağdaki
    # herkes senin API anahtarınla, senin hesabına özet yaptırabilir.
    host = "127.0.0.1"
    adres = f"http://{host}:{args.port}"
    print(f"Belge Özetleyici çalışıyor: {adres}  (durdurmak için Ctrl+C)")
    if not args.tarayici_acma:
        threading.Timer(1.0, lambda: webbrowser.open(adres)).start()
    uvicorn.run(uygulama_olustur(), host=host, port=args.port, log_level="warning", server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
