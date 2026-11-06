"""Word (.docx) ve PowerPoint (.pptx) okuyucuları."""

from __future__ import annotations

import io

from .temel import OkumaHatasi, OkumaSonucu, imzayi_dogrula, metni_temizle, zip_guvenligini_dogrula


def word_oku(veri: bytes, ad: str) -> OkumaSonucu:
    imzayi_dogrula(veri, "zip", ad)
    zip_guvenligini_dogrula(veri, ad)
    try:
        from docx import Document
        belge = Document(io.BytesIO(veri))
    except Exception as hata:  # python-docx bozuk dosyada farklı hatalar fırlatabilir
        raise OkumaHatasi(f"{ad}: Word dosyası açılamadı ({type(hata).__name__}).") from hata

    notlar: list[str] = []
    gizli = 0
    parcalar: list[str] = []

    def paragraf_metni(paragraf) -> str:
        nonlocal gizli
        yazilar = []
        for run in paragraf.runs:
            # "Gizli" biçimli yazı Word'de görünmez ama dosyada durur. Modele göndermiyoruz:
            # okurun göremediği bir talimat saklamanın klasik yolu.
            if run.font.hidden:
                gizli += 1
                continue
            yazilar.append(run.text)
        return "".join(yazilar) if paragraf.runs else paragraf.text

    for bolum in belge.sections:
        for p in bolum.header.paragraphs:
            if p.text.strip():
                parcalar.append(f"[Üst bilgi] {paragraf_metni(p)}")

    for p in belge.paragraphs:
        metin = paragraf_metni(p)
        if not metin.strip():
            continue
        stil = (p.style.name or "").lower() if p.style is not None else ""
        if stil.startswith(("heading", "başlık", "title")):
            metin = f"## {metin}"
        parcalar.append(metin)

    for sira, tablo in enumerate(belge.tables, start=1):
        satirlar = []
        for satir in tablo.rows:
            hucreler = [h.text.strip().replace("\n", " ").replace("|", "/") for h in satir.cells]
            satirlar.append("| " + " | ".join(hucreler) + " |")
        if satirlar:
            parcalar.append(f"\n[Tablo {sira}]\n" + "\n".join(satirlar))

    if gizli:
        notlar.append(f"{gizli} gizli biçimli yazı parçası okunmadı (Word'de görünmeyen metin).")
    return OkumaSonucu(metni_temizle("\n\n".join(parcalar), notlar), "word", notlar)


def powerpoint_oku(veri: bytes, ad: str) -> OkumaSonucu:
    imzayi_dogrula(veri, "zip", ad)
    zip_guvenligini_dogrula(veri, ad)
    try:
        from pptx import Presentation
        sunum = Presentation(io.BytesIO(veri))
    except Exception as hata:
        raise OkumaHatasi(f"{ad}: PowerPoint dosyası açılamadı ({type(hata).__name__}).") from hata

    parcalar: list[str] = []
    notlu = 0
    for sira, slayt in enumerate(sunum.slides, start=1):
        satirlar = [f"## Slayt {sira}"]
        for sekil in slayt.shapes:
            if getattr(sekil, "has_text_frame", False) and sekil.text_frame.text.strip():
                satirlar.append(sekil.text_frame.text.strip())
            if getattr(sekil, "has_table", False):
                for satir in sekil.table.rows:
                    satirlar.append("| " + " | ".join(h.text.strip().replace("|", "/") for h in satir.cells) + " |")
        if slayt.has_notes_slide:
            not_metni = slayt.notes_slide.notes_text_frame.text.strip()
            if not_metni:
                notlu += 1
                satirlar.append(f"[Konuşmacı notu] {not_metni}")
        parcalar.append("\n".join(satirlar))

    notlar = [f"{len(sunum.slides)} slayt okundu."]
    if notlu:
        notlar.append(f"{notlu} slaydın konuşmacı notları da dahil edildi.")
    return OkumaSonucu(metni_temizle("\n\n".join(parcalar), notlar), "powerpoint", notlar)
