"""Web arayüzünü başlatır:  python -m ozetleyici.web"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser


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
