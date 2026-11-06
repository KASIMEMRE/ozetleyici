// Belge Özetleyici arayüzü.
// Güvenlik: belgeden veya modelden gelen hiçbir metin HTML olarak eklenmez;
// her şey textContent ile yazılır (XSS'e karşı). innerHTML kullanılmaz.
"use strict";

const OTURUM = document.querySelector('meta[name="oturum"]').content;
const $ = (id) => document.getElementById(id);
const el = {
  durum: $("durum"), dosya: $("dosya"), birak: $("birak"), birakMetin: $("birak-metin"), birakAlt: $("birak-alt"),
  ozetle: $("ozetle"), ozet: $("ozet"), notlar: $("notlar"), hata: $("hata"), olcum: $("olcum"),
  kopyala: $("kopyala"), indir: $("indir"), kisisel: $("kisisel"), kisiselListe: $("kisisel-liste"),
  yineDe: $("yine-de"), vazgec: $("vazgec"), tesseractUyari: $("tesseract-uyari"),
};

let secilenDosya = null;
let sonSonuc = null;
let enBuyukMB = 25;
let calisiyor = false;
let ayarHatasi = null;

function api(yol, secenekler = {}) {
  return fetch(yol, { ...secenekler, headers: { ...(secenekler.headers || {}), "X-Oturum-Anahtari": OTURUM } });
}

async function durumuYukle() {
  try {
    const c = await api("/api/durum");
    if (!c.ok) throw new Error((await c.json()).hata || c.statusText);
    const d = await c.json();
    enBuyukMB = d.en_buyuk_mb;
    el.birakAlt.textContent = `${d.desteklenen.join(" ")} · en fazla ${d.en_buyuk_mb} MB`;
    el.dosya.accept = d.desteklenen.join(",");
    el.tesseractUyari.hidden = d.tesseract;
    ayarHatasi = d.ayar_hatasi;
    if (d.ayar_hatasi) {
      el.durum.textContent = "Ayar eksik: .env dosyasını kontrol et";
      el.durum.title = d.ayar_hatasi;
      el.durum.className = "durum kotu";
    } else {
      el.durum.textContent = `Model: ${d.model}`;
      el.durum.className = "durum iyi";
    }
  } catch (h) {
    el.durum.textContent = "Sunucuya bağlanılamadı";
    el.durum.className = "durum kotu";
  }
  dugmeleriGuncelle();
}

function dugmeleriGuncelle() {
  el.ozetle.disabled = !secilenDosya || calisiyor;
  el.ozetle.textContent = calisiyor ? "Özetleniyor…" : "Özetle";
  el.kopyala.disabled = !sonSonuc;
  el.indir.disabled = !sonSonuc;
}

function dosyaSec(dosya) {
  if (!dosya) return;
  if (dosya.size > enBuyukMB * 1024 * 1024) {
    hataGoster(`Dosya çok büyük: ${(dosya.size / 1048576).toFixed(1)} MB (sınır ${enBuyukMB} MB).`);
    return;
  }
  secilenDosya = dosya;
  el.birakMetin.textContent = dosya.name;
  el.birakAlt.textContent = `${(dosya.size / 1024).toFixed(0)} KB · değiştirmek için tıkla`;
  el.birak.classList.add("secili");
  hataGoster(null);
  dugmeleriGuncelle();
}

function hataGoster(mesaj) {
  el.hata.hidden = !mesaj;
  el.hata.textContent = mesaj || "";
}

function notEkle(mesaj, uyari = false) {
  const li = document.createElement("li");
  li.textContent = mesaj;
  if (uyari) li.className = "uyari";
  el.notlar.appendChild(li);
}

function olcumGoster(s) {
  el.olcum.replaceChildren();
  const satirlar = [
    ["Süre", `${s.sure_sn} sn`],
    ["Token", s.girdi_token != null ? `${s.girdi_token} + ${s.cikti_token}` : "bildirilmedi"],
    ["Maliyet", s.maliyet_usd != null ? `$${s.maliyet_usd.toFixed(6)}` : "fiyat ayarı yok"],
    ["Model", s.kullanilan_modeller.join(", ")],
    ["Tür", s.belge_turu],
  ];
  if (s.ocr_sayfa_sayisi) satirlar.push(["OCR", `${s.ocr_sayfa_sayisi} sayfa/görsel`]);
  for (const [ad, deger] of satirlar) {
    const kutu = document.createElement("div");
    const dt = document.createElement("dt"); dt.textContent = ad;
    const dd = document.createElement("dd"); dd.textContent = deger;
    kutu.append(dt, dd);
    el.olcum.appendChild(kutu);
  }
  el.olcum.hidden = false;
}

function secim(ad) {
  return document.querySelector(`input[name="${ad}"]:checked`).value;
}

async function ozetle(yineDeGonder = false) {
  if (!secilenDosya || calisiyor) return;
  if (ayarHatasi) { hataGoster(ayarHatasi); return; }
  calisiyor = true; sonSonuc = null;
  el.notlar.replaceChildren(); el.olcum.hidden = true; el.kisisel.hidden = true; hataGoster(null);
  el.ozet.textContent = ""; el.ozet.classList.remove("bos"); el.ozet.classList.add("yaziyor");
  dugmeleriGuncelle();

  const parametre = new URLSearchParams({
    ad: secilenDosya.name, uzunluk: secim("uzunluk"), ocr: secim("ocr"), yine_de_gonder: yineDeGonder ? "1" : "0",
  });
  try {
    const cevap = await api(`/api/ozetle?${parametre}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: secilenDosya,
    });
    if (!cevap.ok) {
      let mesaj = cevap.statusText;
      try { mesaj = (await cevap.json()).hata || mesaj; } catch (_) { /* gövde JSON değil */ }
      throw new Error(mesaj);
    }
    // Sunucu her satırda bir JSON olay gönderir (NDJSON).
    const okuyucu = cevap.body.getReader();
    const cozucu = new TextDecoder();
    let tampon = "";
    for (;;) {
      const { value, done } = await okuyucu.read();
      if (done) break;
      tampon += cozucu.decode(value, { stream: true });
      let satirSonu;
      while ((satirSonu = tampon.indexOf("\n")) >= 0) {
        const satir = tampon.slice(0, satirSonu).trim();
        tampon = tampon.slice(satirSonu + 1);
        if (satir) olayIsle(JSON.parse(satir));
      }
    }
  } catch (h) {
    hataGoster(h.message || String(h));
  } finally {
    calisiyor = false;
    el.ozet.classList.remove("yaziyor");
    if (!el.ozet.textContent) { el.ozet.classList.add("bos"); el.ozet.textContent = "Özet yok."; }
    dugmeleriGuncelle();
  }
}

function olayIsle(o) {
  switch (o.tip) {
    case "bilgi": notEkle(o.mesaj); break;
    case "not": notEkle(o.mesaj); break;
    case "uyari": notEkle(o.mesaj, true); break;
    case "parca": el.ozet.textContent += o.metin; break;
    case "sifirla":
      el.ozet.textContent = "";
      notEkle("Bağlantı yarıda kesildi; özet baştan alınıyor.", true);
      break;
    case "kisisel_veri":
      el.kisiselListe.textContent = Object.entries(o.bulgular).map(([tur, adet]) => `${adet} ${tur}`).join(", ") + ".";
      el.kisisel.hidden = false;
      el.ozet.textContent = "";
      break;
    case "bitti":
      sonSonuc = o.sonuc;
      el.ozet.textContent = o.sonuc.ozet;
      olcumGoster(o.sonuc);
      break;
    case "hata": hataGoster(o.mesaj); break;
  }
}

// --- olaylar
el.dosya.addEventListener("change", () => dosyaSec(el.dosya.files[0]));
for (const ad of ["dragenter", "dragover"]) {
  el.birak.addEventListener(ad, (e) => { e.preventDefault(); el.birak.classList.add("uzerinde"); });
}
for (const ad of ["dragleave", "drop"]) {
  el.birak.addEventListener(ad, (e) => { e.preventDefault(); el.birak.classList.remove("uzerinde"); });
}
el.birak.addEventListener("drop", (e) => dosyaSec(e.dataTransfer.files[0]));
el.ozetle.addEventListener("click", () => ozetle(false));
el.yineDe.addEventListener("click", () => ozetle(true));
el.vazgec.addEventListener("click", () => { el.kisisel.hidden = true; el.ozet.textContent = "Gönderilmedi."; });
el.kopyala.addEventListener("click", async () => {
  if (!sonSonuc) return;
  await navigator.clipboard.writeText(sonSonuc.ozet);
  el.kopyala.textContent = "Kopyalandı";
  setTimeout(() => { el.kopyala.textContent = "Kopyala"; }, 1500);
});
el.indir.addEventListener("click", () => {
  if (!sonSonuc) return;
  const blob = new Blob([JSON.stringify(sonSonuc, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = sonSonuc.kaynak_dosya.replace(/\.[^.]+$/, "") + ".ozet.json";
  a.click();
  URL.revokeObjectURL(a.href);
});

durumuYukle();
