from ozetleyici.gizlilik import kisisel_veri_ipuclari, tckn_gecerli_mi

# Kontrol haneleri geçerli ama gerçek kişiye ait olmayan, test amaçlı üretilmiş numara.
GECERLI_TCKN = "10000000146"


def test_tckn_kontrol_hanesi():
    assert tckn_gecerli_mi(GECERLI_TCKN)
    assert not tckn_gecerli_mi("12345678901")  # rastgele 11 hane
    assert not tckn_gecerli_mi("01234567890")  # 0 ile başlayamaz


def test_ipuclari_bulunur_ama_degerler_dondurulmez():
    metin = (f"TCKN {GECERLI_TCKN}, tel 0532 123 45 67, e-posta deneme@ornek.com.tr, "
             "IBAN TR33 0006 1005 1978 6457 8413 26")
    bulgular = kisisel_veri_ipuclari(metin)
    assert bulgular == {"T.C. kimlik no": 1, "IBAN": 1, "e-posta": 1, "cep telefonu": 1}
    assert all(isinstance(v, int) for v in bulgular.values())


def test_siradan_metinde_yanlis_alarm_yok():
    metin = "Politika 1 Ocak 2027'de yürürlüğe girer. Aylık 400 TL destek. Saat 10:00-16:00. Sipariş no 12345678901."
    assert kisisel_veri_ipuclari(metin) == {}


def test_ornek_belge_temiz():
    from pathlib import Path
    metin = (Path(__file__).parent.parent / "ornekler" / "ornek_belge.txt").read_text(encoding="utf-8")
    assert kisisel_veri_ipuclari(metin) == {}
