"""Belgeyi sağlayıcıya göndermeden önce kişisel veri ipuçlarını arar.

Bu kontrol kaba bir ön elemedir, maskeleme değildir. Amaç kullanıcıyı uyarmak:
ücretsiz LLM katmanlarında gönderilen içerik sağlayıcı tarafından model
geliştirmede kullanılabilir ve insanlar tarafından okunabilir.
İsim ve adres gibi verileri yakalamaz; asıl maskeleme Proje 1'in konusu.
"""

from __future__ import annotations

import re

_EPOSTA = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE)
_TELEFON = re.compile(r"(?<!\d)(?:\+90|0)?\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
_ON_BIR_HANE = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")


def tckn_gecerli_mi(sayi: str) -> bool:
    """T.C. kimlik numarasının kontrol hanelerini doğrular (rastgele 11 haneli sayıları eler)."""
    if len(sayi) != 11 or not sayi.isdigit() or sayi[0] == "0":
        return False
    h = [int(c) for c in sayi]
    onuncu = ((h[0] + h[2] + h[4] + h[6] + h[8]) * 7 - (h[1] + h[3] + h[5] + h[7])) % 10
    on_birinci = sum(h[:10]) % 10
    return h[9] == onuncu and h[10] == on_birinci


def kisisel_veri_ipuclari(metin: str) -> dict[str, int]:
    """Bulunan kişisel veri türlerini ve adetlerini döndürür. Bulunan değerleri döndürmez."""
    bulgular = {
        "T.C. kimlik no": sum(1 for s in _ON_BIR_HANE.findall(metin) if tckn_gecerli_mi(s)),
        "IBAN": len(_IBAN.findall(metin)),
        "e-posta": len(_EPOSTA.findall(metin)),
        "cep telefonu": len(_TELEFON.findall(metin)),
    }
    return {tur: adet for tur, adet in bulgular.items() if adet}
