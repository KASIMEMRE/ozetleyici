"""Excel (.xlsx) ve CSV okuyucuları.

LLM'ler sayıları toplamakta ve karşılaştırmakta güvenilmezdir. Bu yüzden
tablonun yalnızca bir önizlemesini modele veriyoruz; toplam, ortalama gibi
hesapları Python'da TÜM satırlar üzerinden yapıp sonucu metne ekliyoruz.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from .temel import OkumaHatasi, OkumaSonucu, imzayi_dogrula, metin_kodunu_coz, metni_temizle, zip_guvenligini_dogrula

ONIZLEME_SATIR = 100     # modele gösterilen satır sayısı (sayfa başına)
EN_FAZLA_SUTUN = 30
EN_FAZLA_SATIR = 100_000  # istatistik için okunan en fazla satır
EN_FAZLA_SAYFA = 10
HUCRE_UZUNLUGU = 60


@dataclass
class _Sutun:
    ad: str
    sayilar: list[float] = field(default_factory=list)
    dolu: int = 0


def _sayi(deger) -> float | None:
    if isinstance(deger, bool):
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    if isinstance(deger, str):
        s = deger.strip().replace(" ", "").replace(" ", "")
        # Türkçe biçim: 1.234,56  ->  1234.56
        if s.count(",") == 1 and (s.count(".") == 0 or s.rfind(".") < s.rfind(",")):
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _hucre(deger) -> str:
    if deger is None:
        return ""
    if isinstance(deger, datetime):
        deger = deger.date() if deger.time() == datetime.min.time() else deger
    if isinstance(deger, (date, datetime)):
        return deger.isoformat()
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)
    metin = str(deger).replace("\n", " ").replace("|", "/").strip()
    return metin if len(metin) <= HUCRE_UZUNLUGU else metin[: HUCRE_UZUNLUGU - 1] + "…"


def _bicimle(sayi: float) -> str:
    if sayi.is_integer() and abs(sayi) < 1e15:
        return f"{int(sayi):,}".replace(",", ".")
    return f"{sayi:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def satirlari_metne_cevir(baslik: str, satirlar: list[list], notlar: list[str]) -> str:
    """Bir tabloyu (satır listesi) önizleme + Python'da hesaplanmış istatistiklere çevirir."""
    satirlar = [s for s in satirlar if any(h not in (None, "") for h in s)]
    if not satirlar:
        return f"## {baslik}\n(boş)"
    genislik = min(max(len(s) for s in satirlar), EN_FAZLA_SUTUN)
    satirlar = [list(s[:genislik]) + [None] * (genislik - len(s[:genislik])) for s in satirlar]

    ilk = satirlar[0]
    baslik_var = all(isinstance(h, str) and h.strip() for h in ilk if h is not None) and any(ilk)
    adlar = [_hucre(h) or f"Sütun {i + 1}" for i, h in enumerate(ilk)] if baslik_var else [f"Sütun {i + 1}" for i in range(genislik)]
    veri = satirlar[1:] if baslik_var else satirlar

    sutunlar = [_Sutun(ad) for ad in adlar]
    for satir in veri:
        for sutun, deger in zip(sutunlar, satir):
            if deger not in (None, ""):
                sutun.dolu += 1
                sayi = _sayi(deger)
                if sayi is not None:
                    sutun.sayilar.append(sayi)

    cikti = [f"## {baslik} ({len(veri)} veri satırı × {genislik} sütun)"]
    gosterilen = veri[:ONIZLEME_SATIR]
    cikti.append("| " + " | ".join(adlar) + " |")
    cikti.append("|" + "---|" * genislik)
    for satir in gosterilen:
        cikti.append("| " + " | ".join(_hucre(h) for h in satir) + " |")
    if len(veri) > len(gosterilen):
        cikti.append(f"(… {len(veri) - len(gosterilen)} satır daha var; aşağıdaki istatistikler TÜM satırlardan hesaplandı)")

    istatistik = []
    for s in sutunlar:
        # Sütunun çoğu sayıysa sayısal kabul et
        if s.sayilar and len(s.sayilar) >= max(1, s.dolu * 0.8):
            n = len(s.sayilar)
            istatistik.append(
                f"- {s.ad}: {n} değer, toplam {_bicimle(sum(s.sayilar))}, ortalama {_bicimle(sum(s.sayilar) / n)}, "
                f"en az {_bicimle(min(s.sayilar))}, en çok {_bicimle(max(s.sayilar))}"
            )
    if istatistik:
        cikti.append("\nPython ile hesaplanan istatistikler (bu rakamları aynen kullan, kendin hesap yapma):")
        cikti.extend(istatistik)
    return "\n".join(cikti)


def excel_oku(veri: bytes, ad: str) -> OkumaSonucu:
    imzayi_dogrula(veri, "zip", ad)
    zip_guvenligini_dogrula(veri, ad)
    try:
        import openpyxl
        # read_only: büyük dosyada belleği korur. data_only: formül yerine son hesaplanan değeri okur.
        # keep_vba=False (varsayılan): makrolar asla yüklenmez ve çalıştırılmaz.
        kitap = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except Exception as hata:
        raise OkumaHatasi(f"{ad}: Excel dosyası açılamadı ({type(hata).__name__}).") from hata

    notlar: list[str] = []
    parcalar: list[str] = []
    try:
        sayfalar = kitap.worksheets
        gizli = [s.title for s in sayfalar if s.sheet_state != "visible"]
        gorunur = [s for s in sayfalar if s.sheet_state == "visible"]
        if gizli:
            notlar.append(f"Gizli sayfalar okunmadı: {', '.join(gizli)}.")
        if len(gorunur) > EN_FAZLA_SAYFA:
            notlar.append(f"{len(gorunur)} sayfanın yalnızca ilk {EN_FAZLA_SAYFA} tanesi okundu.")
        for sayfa in gorunur[:EN_FAZLA_SAYFA]:
            satirlar = []
            for sira, satir in enumerate(sayfa.iter_rows(values_only=True)):
                if sira >= EN_FAZLA_SATIR:
                    notlar.append(f"'{sayfa.title}': ilk {EN_FAZLA_SATIR:,} satır okundu.".replace(",", "."))
                    break
                satirlar.append(list(satir))
            parcalar.append(satirlari_metne_cevir(f"Sayfa: {sayfa.title}", satirlar, notlar))
    finally:
        kitap.close()

    notlar.insert(0, f"{min(len(gorunur), EN_FAZLA_SAYFA)} sayfa okundu; her sayfadan en fazla {ONIZLEME_SATIR} satır modele gösterildi, istatistikler tüm satırlardan hesaplandı.")
    return OkumaSonucu(metni_temizle("\n\n".join(parcalar), notlar), "excel", notlar)


def csv_oku(veri: bytes, ad: str) -> OkumaSonucu:
    metin = metin_kodunu_coz(veri, ad)
    ornek = metin[:5000]
    try:
        # Türkçe Excel CSV'yi genelde ";" ile kaydeder; ayırıcıyı tahmin ediyoruz.
        lehce = csv.Sniffer().sniff(ornek, delimiters=";,\t|")
    except csv.Error:
        lehce = csv.excel
    satirlar = []
    for sira, satir in enumerate(csv.reader(io.StringIO(metin), lehce)):
        if sira >= EN_FAZLA_SATIR:
            break
        satirlar.append(satir)
    notlar = [f"CSV okundu (ayırıcı: {lehce.delimiter!r})."]
    return OkumaSonucu(metni_temizle(satirlari_metne_cevir(ad, satirlar, notlar), notlar), "csv", notlar)
