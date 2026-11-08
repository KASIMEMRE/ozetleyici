// Belge Özetleyici arayüzü.
// Güvenlik: belgeden veya modelden gelen hiçbir metin HTML olarak eklenmez. Özetteki başlık ve
// maddeler bile tek tek DOM öğesi oluşturularak ve textContent ile yazılır (XSS'e karşı).
"use strict";

const OTURUM = document.querySelector('meta[name="oturum"]').content;
const $ = (id) => document.getElementById(id);
const el = Object.fromEntries([
  "durum", "model", "dosya", "birak", "birak-bos", "birak-dolu", "birak-alt", "dosya-tur", "dosya-ad", "dosya-boyut",
  "odak", "ocr-ayar", "ses-ayar", "tesseract-uyari", "whisper-uyari", "ozetle", "gecmis", "gecmis-liste",
  "sekme-ozet", "sekme-kaynak", "panel-ozet", "panel-kaynak", "kopyala", "indir", "indir-menu",
  "ilerleme", "sure", "durdur", "son-bilgi", "uyari-kisisel", "kisisel-liste", "kisisel-gonder", "kisisel-vazgec",
  "uyari-butce", "butce-gereken", "butce-sinir", "butce-devam", "butce-vazgec", "hata", "ozet", "kaynak",
  "kaynak-bilgi", "notlar-kutu", "notlar", "not-sayisi", "iz", "iz-yerel", "iz-disari", "olcum", "birakma-katmani",
].map((id) => [id.replace(/-([a-z])/g, (_, h) => h.toUpperCase()), $(id)]));

const MODEL_ANAHTARI = "ozetleyici.model";
const TURLER = {
  ".pdf": "PDF", ".docx": "Word", ".xlsx": "Excel", ".xlsm": "Excel", ".pptx": "PowerPoint", ".csv": "CSV",
  ".txt": "Metin", ".md": "Metin", ".png": "Görsel", ".jpg": "Görsel", ".jpeg": "Görsel",
  ".mp3": "Ses", ".wav": "Ses", ".m4a": "Ses", ".ogg": "Ses", ".opus": "Ses", ".flac": "Ses",
  ".mp4": "Video", ".mov": "Video", ".mkv": "Video", ".webm": "Video", ".avi": "Video",
};
const OCR_TURLERI = new Set(["PDF", "Görsel"]);
const SES_TURLERI = new Set(["Ses", "Video"]);

const durum = {
  dosya: null, calisiyor: false, ayarHatasi: null, enBuyukMB: 25, enBuyukMedyaMB: 200,
  onay: { yineDe: false, istekSiniri: null },
  iptal: null, sayac: null, baslangic: 0,
  gorunen: null,   // ekrandaki sonuç: { ad, sonuc, kaynak, notlar, zaman }
  gecmis: [],      // bu oturumdaki sonuçlar (yalnızca bellekte)
};

// ---------------------------------------------------------------- yardımcılar

function api(yol, secenekler = {}) {
  return fetch(yol, { ...secenekler, headers: { ...(secenekler.headers || {}), "X-Oturum-Anahtari": OTURUM } });
}
const uzantisi = (ad) => ((ad.match(/\.[^.]+$/) || [""])[0]).toLowerCase();
const sayiYaz = (n) => Number(n).toLocaleString("tr-TR");
function boyutYaz(bayt) {
  return bayt >= 1048576 ? `${(bayt / 1048576).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`
    : `${Math.max(1, Math.round(bayt / 1024))} KB`;
}
function sureYaz(sn) {
  const s = Math.round(sn), dk = Math.floor(s / 60);
  return dk ? `${dk} dk ${s % 60} sn` : `${s} sn`;
}
const secim = (ad) => document.querySelector(`input[name="${ad}"]:checked`).value;
function yeni(etiket, metin, sinif) {
  const e = document.createElement(etiket);
  if (metin != null) e.textContent = metin;
  if (sinif) e.className = sinif;
  return e;
}

// ---------------------------------------------------------------- özetteki basit biçim (güvenli)

// Satır içi **kalın** yazıyı DOM düğümlerine çevirir; geri kalan her şey düz metindir.
function satirIci(metin, kap) {
  const parcalar = metin.split(/(\*\*[^*]+\*\*)/g);
  for (const p of parcalar) {
    if (!p) continue;
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) kap.appendChild(yeni("strong", p.slice(2, -2)));
    else kap.appendChild(document.createTextNode(p.replace(/(^|\s)\*(\S[^*]*\S)\*(?=\s|$)/g, "$1$2")));
  }
  return kap;
}

// Modelin yazdığı Markdown'ın küçük bir alt kümesini (başlık, madde, numara, paragraf) çizer.
function bicimliCiz(metin, kok) {
  kok.replaceChildren();
  let liste = null, listeTuru = null, paragraf = [];
  const paragrafiBitir = () => {
    if (paragraf.length) { kok.appendChild(satirIci(paragraf.join(" "), yeni("p"))); paragraf = []; }
  };
  const listeyiBitir = () => { liste = null; listeTuru = null; };
  for (const hamSatir of metin.split("\n")) {
    const satir = hamSatir.trim();
    let m;
    if (!satir) { paragrafiBitir(); listeyiBitir(); continue; }
    if ((m = satir.match(/^#{1,6}\s+(.*)$/))) {
      paragrafiBitir(); listeyiBitir();
      kok.appendChild(satirIci(m[1].replace(/\s*#+$/, ""), yeni(satir.startsWith("###") ? "h4" : "h3")));
    } else if ((m = satir.match(/^(?:[-*•]|(\d+)[.)])\s+(.*)$/))) {
      paragrafiBitir();
      const tur = m[1] ? "ol" : "ul";
      if (!liste || listeTuru !== tur) { liste = kok.appendChild(yeni(tur)); listeTuru = tur; }
      liste.appendChild(satirIci(m[2], yeni("li")));
    } else {
      listeyiBitir();
      paragraf.push(satir);
    }
  }
  paragrafiBitir();
}

// ---------------------------------------------------------------- başlangıç

async function durumuYukle() {
  try {
    const c = await api("/api/durum");
    if (!c.ok) throw new Error((await c.json()).hata || c.statusText);
    const d = await c.json();
    durum.enBuyukMB = d.en_buyuk_mb;
    durum.enBuyukMedyaMB = d.en_buyuk_medya_mb;
    el.dosya.accept = d.desteklenen.join(",");
    el.birakAlt.textContent = `PDF, Word, Excel, PowerPoint, görsel, ses, video (en fazla ${d.en_buyuk_mb} MB, ses/video ${d.en_buyuk_medya_mb} MB)`;
    el.tesseractUyari.hidden = d.tesseract;
    el.whisperUyari.hidden = d.whisper.kurulu;
    durum.ayarHatasi = d.ayar_hatasi;
    if (d.ayar_hatasi) {
      el.durum.textContent = ".env ayarı eksik";
      el.durum.title = d.ayar_hatasi;
      el.durum.className = "durum kotu";
      el.model.replaceChildren(new Option("ayar yok"));
    } else {
      el.durum.textContent = "Hazır";
      el.durum.className = "durum iyi";
      modelleriYukle();
    }
  } catch (h) {
    el.durum.textContent = "Sunucuya bağlanılamadı";
    el.durum.className = "durum kotu";
  }
  dugmeleriGuncelle();
}

async function modelleriYukle() {
  try {
    const c = await api("/api/modeller");
    if (!c.ok) throw new Error((await c.json()).hata || c.statusText);
    const d = await c.json();
    let kayitli = null;
    try { kayitli = localStorage.getItem(MODEL_ANAHTARI); } catch (_) { /* depolama kapalı olabilir */ }
    el.model.replaceChildren(...d.modeller.map((ad) => new Option(ad === d.varsayilan ? `${ad} (varsayılan)` : ad, ad)));
    el.model.value = d.modeller.includes(kayitli) ? kayitli : d.varsayilan;
    el.model.disabled = d.modeller.length < 2;
    el.model.title = d.hata || "Liste, anahtarının erişebildiği ve metin üreten modellerden oluşur.";
  } catch (h) {
    el.model.replaceChildren(new Option("liste alınamadı"));
    el.model.title = h.message || String(h);
  }
}

// ---------------------------------------------------------------- dosya seçimi

function dosyaSec(dosya) {
  if (!dosya || durum.calisiyor) return;
  const tur = TURLER[uzantisi(dosya.name)];
  if (!tur) {
    hataGoster(`${dosya.name}: bu dosya türü desteklenmiyor. PDF, Word, Excel, PowerPoint, CSV, metin, görsel, ses veya video seç.`);
    return;
  }
  const sinirMB = SES_TURLERI.has(tur) ? durum.enBuyukMedyaMB : durum.enBuyukMB;
  if (dosya.size > sinirMB * 1024 * 1024) {
    hataGoster(`${dosya.name} ${boyutYaz(dosya.size)}; bu tür için sınır ${sinirMB} MB.`);
    return;
  }
  durum.dosya = dosya;
  durum.onay = { yineDe: false, istekSiniri: null };
  el.dosyaTur.textContent = tur;
  el.dosyaAd.textContent = dosya.name;
  el.dosyaAd.title = dosya.name;
  el.dosyaBoyut.textContent = boyutYaz(dosya.size);
  el.birakBos.hidden = true;
  el.birakDolu.hidden = false;
  el.birak.classList.add("dolu");
  // Yalnızca bu dosya türünde anlamı olan ayarları göster
  el.ocrAyar.hidden = !OCR_TURLERI.has(tur);
  el.sesAyar.hidden = !SES_TURLERI.has(tur);
  hataGoster(null);
  dugmeleriGuncelle();
}

// ---------------------------------------------------------------- ekran durumu

function dugmeleriGuncelle() {
  el.ozetle.disabled = !durum.dosya || durum.calisiyor || !!durum.ayarHatasi;
  el.ozetle.textContent = durum.calisiyor ? "Özetleniyor…" : "Özetle";
  const sonucVar = !!(durum.gorunen && durum.gorunen.sonuc);
  el.kopyala.disabled = !sonucVar;
  el.indir.disabled = !sonucVar;
  el.sekmeKaynak.disabled = !(durum.gorunen && durum.gorunen.kaynak);
}

function hataGoster(mesaj) {
  el.hata.hidden = !mesaj;
  el.hata.textContent = mesaj || "";
}

function sekmeSec(hangisi) {
  const ozet = hangisi === "ozet";
  el.sekmeOzet.setAttribute("aria-selected", String(ozet));
  el.sekmeKaynak.setAttribute("aria-selected", String(!ozet));
  el.sekmeOzet.tabIndex = ozet ? 0 : -1;
  el.sekmeKaynak.tabIndex = ozet ? -1 : 0;
  el.panelOzet.hidden = !ozet;
  el.panelKaynak.hidden = ozet;
}

function notEkle(mesaj, uyari = false) {
  const li = yeni("li", mesaj, uyari ? "uyari-not" : null);
  el.notlar.appendChild(li);
  el.notSayisi.textContent = String(el.notlar.children.length);
  el.notlarKutu.hidden = false;
  if (durum.gorunen) durum.gorunen.notlar.push({ mesaj, uyari });
}

function asama(ad) {
  let gecti = true;
  for (const li of el.ilerleme.querySelectorAll("li")) {
    if (li.dataset.asama === ad) { li.dataset.durum = "suruyor"; gecti = false; }
    else li.dataset.durum = gecti ? "bitti" : "";
  }
}

function ekraniTemizle() {
  el.notlar.replaceChildren(); el.notSayisi.textContent = "0"; el.notlarKutu.hidden = true;
  el.uyariKisisel.hidden = true; el.uyariButce.hidden = true; el.iz.hidden = true;
  el.kaynak.textContent = ""; el.kaynakBilgi.textContent = "";
  el.ozet.replaceChildren(); el.ozet.classList.remove("yaziyor");
  hataGoster(null);
  sekmeSec("ozet");
}

function bosDurum(baslik, metin) {
  el.ozet.replaceChildren(yeni("p", metin ? `${baslik} ${metin}` : baslik, "bos-durum"));
}

// ---------------------------------------------------------------- veri izi

function izGoster(s, durdu = null) {
  const yerel = [], disari = [];
  const kalem = (liste, baslik, aciklama) => liste.push([baslik, aciklama]);
  kalem(yerel, "Dosya", "Diske kaydedilmedi");
  if (s) {
    if ((s.belge_turu === "ses" || s.belge_turu === "video") && !s.saglayiciya_gonderilen_ses_parcasi) {
      kalem(yerel, `${s.belge_turu === "video" ? "Videonun sesi" : "Ses kaydı"} (${sureYaz(s.ses_suresi_sn)})`, "Whisper ile yazıya döküldü");
    }
    if (s.ocr_sayfa_sayisi && !s.saglayiciya_gonderilen_gorsel) {
      kalem(yerel, `${s.ocr_sayfa_sayisi} taranmış sayfa`, "Tesseract ile okundu");
    }
  }

  if (durdu) {
    kalem(disari, "Hiçbir şey", durdu);
  } else if (s) {
    kalem(disari, `${sayiYaz(s.saglayiciya_giden_karakter)} karakter metin`, s.kullanilan_modeller.join(", "));
    if (s.saglayiciya_gonderilen_gorsel) kalem(disari, `${s.saglayiciya_gonderilen_gorsel} sayfa görüntüsü`, "");
    if (s.saglayiciya_gonderilen_ses_parcasi) kalem(disari, `${s.saglayiciya_gonderilen_ses_parcasi} ses parçası (5 dk)`, "");
  }
  const ciz = (ul, liste, bos) => {
    ul.replaceChildren(...liste.map(([b, a]) => {
      const li = yeni("li", null, bos ? "bos" : null);
      li.append(document.createTextNode(b));
      if (a) li.append(yeni("small", a));
      return li;
    }));
  };
  ciz(el.izYerel, yerel, false);
  ciz(el.izDisari, disari, !!durdu);

  el.olcum.replaceChildren();
  if (s) {
    const olcumler = [
      ["Süre", sureYaz(s.sure_sn)],
      ["İstek", String(s.kullanilan_istek)],
      ["Token", s.girdi_token != null ? `${sayiYaz(s.girdi_token + (s.okuma_girdi_token || 0))} girdi, ${sayiYaz(s.cikti_token + (s.okuma_cikti_token || 0))} çıktı` : "bildirilmedi"],
      ["Maliyet", s.maliyet_usd != null ? `${s.maliyet_usd.toFixed(6)} USD` : "hesaplanmadı"],
    ];
    for (const [ad, deger] of olcumler) {
      const kutu = yeni("div");
      kutu.append(yeni("dt", ad), yeni("dd", deger));
      el.olcum.appendChild(kutu);
    }
  }
  el.iz.hidden = false;
}

// ---------------------------------------------------------------- özetleme

async function ozetle() {
  if (!durum.dosya || durum.calisiyor || durum.ayarHatasi) return;
  durum.calisiyor = true;
  durum.gorunen = { ad: durum.dosya.name, tur: el.dosyaTur.textContent, sonuc: null, kaynak: "", notlar: [], zaman: new Date() };
  ekraniTemizle();
  el.ozet.classList.add("yaziyor");
  el.ilerleme.hidden = false;
  el.sonBilgi.textContent = "";
  asama("okuma");
  durum.baslangic = Date.now();
  el.sure.textContent = "0 sn";
  durum.sayac = setInterval(() => { el.sure.textContent = sureYaz((Date.now() - durum.baslangic) / 1000); }, 1000);
  durum.iptal = new AbortController();
  dugmeleriGuncelle();

  const p = new URLSearchParams({
    ad: durum.dosya.name, uzunluk: secim("uzunluk"), ocr: secim("ocr"), ses: secim("ses"),
    yine_de_gonder: durum.onay.yineDe ? "1" : "0",
  });
  if (durum.onay.istekSiniri) p.set("istek_siniri", String(durum.onay.istekSiniri));
  if (!el.model.disabled && el.model.value) p.set("model", el.model.value);
  const odak = el.odak.value.trim();
  if (odak) p.set("odak", odak);

  let akanMetin = "", cizimBekliyor = false;
  const ciz = () => { cizimBekliyor = false; bicimliCiz(akanMetin, el.ozet); };

  try {
    const cevap = await api(`/api/ozetle?${p}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: durum.dosya,
      signal: durum.iptal.signal,
    });
    if (!cevap.ok) {
      let mesaj = cevap.statusText;
      try { mesaj = (await cevap.json()).hata || mesaj; } catch (_) { /* gövde JSON değil */ }
      throw new Error(mesaj);
    }
    const okuyucu = cevap.body.getReader();
    const cozucu = new TextDecoder();
    let tampon = "";
    for (;;) {
      const { value, done } = await okuyucu.read();
      if (done) break;
      tampon += cozucu.decode(value, { stream: true });
      let n;
      while ((n = tampon.indexOf("\n")) >= 0) {
        const satir = tampon.slice(0, n).trim();
        tampon = tampon.slice(n + 1);
        if (!satir) continue;
        const o = JSON.parse(satir);
        switch (o.tip) {
          case "asama": asama(o.ad); break;
          case "bilgi": el.sonBilgi.textContent = o.mesaj; break;
          case "uyari": el.sonBilgi.textContent = o.mesaj; notEkle(o.mesaj, true); break;
          case "not": notEkle(o.mesaj); break;
          case "kaynak":
            durum.gorunen.kaynak = o.metin;
            el.kaynak.textContent = o.metin;
            el.kaynakBilgi.textContent = `${sayiYaz(o.metin.length)} karakter${o.kesildi ? " (burada kısaltıldı, modele tamamı gitti)" : ""}`;
            dugmeleriGuncelle();
            break;
          case "parca":
            akanMetin += o.metin;
            if (!cizimBekliyor) { cizimBekliyor = true; requestAnimationFrame(ciz); }
            break;
          case "sifirla":
            akanMetin = "";
            el.ozet.replaceChildren();
            notEkle("Bağlantı yarıda kesildi; özet baştan alındı.", true);
            break;
          case "kisisel_veri":
            el.kisiselListe.textContent = Object.entries(o.bulgular).map(([t, a]) => `${a} ${t}`).join(", ") + ".";
            el.uyariKisisel.hidden = false;
            izGoster(null, "Onayını bekliyor");
            break;
          case "onay_gerekli":
            el.butceGereken.textContent = String(o.gereken);
            el.butceSinir.textContent = String(o.sinir);
            el.butceDevam.textContent = `Devam et (${o.gereken} istek)`;
            el.butceDevam.dataset.gereken = String(o.gereken);
            el.uyariButce.hidden = false;
            izGoster(null, "Onayını bekliyor");
            break;
          case "bitti":
            durum.gorunen.sonuc = o.sonuc;
            bicimliCiz(o.sonuc.ozet, el.ozet);
            izGoster(o.sonuc);
            gecmiseEkle(durum.gorunen);
            break;
          case "hata": hataGoster(o.mesaj); break;
        }
      }
    }
  } catch (h) {
    if (h.name === "AbortError") {
      notEkle("Durduruldu.", true);
      if (!akanMetin) bosDurum("Durduruldu.");
    } else {
      hataGoster(h.message || String(h));
    }
  } finally {
    clearInterval(durum.sayac);
    durum.calisiyor = false;
    durum.iptal = null;
    el.ozet.classList.remove("yaziyor");
    el.ilerleme.hidden = true;
    if (!el.ozet.childNodes.length && el.hata.hidden && el.uyariKisisel.hidden && el.uyariButce.hidden) {
      bosDurum("Özet çıkmadı.", "Ayrıntı için okuma notlarına bak.");
    }
    // Uyarı açıkken altta ayrıca boş durum gösterme: aynı bilgi uyarıda ve veri izinde var.
    dugmeleriGuncelle();
  }
}

// ---------------------------------------------------------------- geçmiş

function gecmiseEkle(kayit) {
  durum.gecmis.unshift({ ...kayit, notlar: [...kayit.notlar] });
  durum.gecmis = durum.gecmis.slice(0, 20);
  gecmisiCiz();
}

function gecmisiCiz() {
  el.gecmis.hidden = durum.gecmis.length === 0;
  el.gecmisListe.replaceChildren(...durum.gecmis.map((k, i) => {
    const li = yeni("li");
    const b = yeni("button");
    b.type = "button";
    b.append(yeni("span", k.ad, "g-ad"), yeni("span", k.zaman.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }), "g-saat"));
    b.title = `${k.ad}, ${k.sonuc.kullanilan_modeller.join(", ")}`;
    if (durum.gorunen && durum.gorunen.sonuc === k.sonuc) b.setAttribute("aria-current", "true");
    b.addEventListener("click", () => gecmistenGoster(i));
    li.appendChild(b);
    return li;
  }));
}

function gecmistenGoster(i) {
  if (durum.calisiyor) return;
  const k = durum.gecmis[i];
  ekraniTemizle();
  durum.gorunen = { ...k, notlar: [] };
  bicimliCiz(k.sonuc.ozet, el.ozet);
  el.kaynak.textContent = k.kaynak;
  el.kaynakBilgi.textContent = `${sayiYaz(k.kaynak.length)} karakter`;
  for (const n of k.notlar) notEkle(n.mesaj, n.uyari);
  izGoster(k.sonuc);
  gecmisiCiz();
  dugmeleriGuncelle();
}

// ---------------------------------------------------------------- dışa aktarma

function indir(bicim) {
  const k = durum.gorunen;
  if (!k || !k.sonuc) return;
  const s = k.sonuc;
  const temelAd = k.ad.replace(/\.[^.]+$/, "");
  let icerik, tur, uzanti;
  if (bicim === "json") {
    icerik = JSON.stringify({ ...s, kaynak_metin: k.kaynak }, null, 2); tur = "application/json"; uzanti = "ozet.json";
  } else if (bicim === "md") {
    icerik = `# ${k.ad} özeti\n\n${s.ozet}\n\n---\n\nModel: ${s.kullanilan_modeller.join(", ")}\nOluşturulma: ${s.olusturulma}\n`;
    tur = "text/markdown"; uzanti = "ozet.md";
  } else {
    icerik = `${k.ad} özeti\n\n${s.ozet.replace(/\*\*/g, "").replace(/^#{1,6}\s+/gm, "")}\n`;
    tur = "text/plain"; uzanti = "ozet.txt";
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([icerik], { type: `${tur};charset=utf-8` }));
  a.download = `${temelAd}.${uzanti}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  menuyuKapat();
}

function menuyuKapat() { el.indirMenu.hidden = true; el.indir.setAttribute("aria-expanded", "false"); }

// ---------------------------------------------------------------- olaylar

el.dosya.addEventListener("change", () => { dosyaSec(el.dosya.files[0]); el.dosya.value = ""; });

// Dosya sayfanın herhangi bir yerine bırakılabilir
let surukleSayaci = 0;
const dosyaSurukleniyor = (e) => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
window.addEventListener("dragenter", (e) => {
  if (!dosyaSurukleniyor(e)) return;
  e.preventDefault(); surukleSayaci++; el.birakmaKatmani.hidden = false;
});
window.addEventListener("dragover", (e) => { if (dosyaSurukleniyor(e)) e.preventDefault(); });
window.addEventListener("dragleave", () => { if (--surukleSayaci <= 0) { surukleSayaci = 0; el.birakmaKatmani.hidden = true; } });
window.addEventListener("drop", (e) => {
  e.preventDefault(); surukleSayaci = 0; el.birakmaKatmani.hidden = true;
  if (e.dataTransfer.files.length) dosyaSec(e.dataTransfer.files[0]);
});

el.ozetle.addEventListener("click", ozetle);
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); ozetle(); }
  if (e.key === "Escape") menuyuKapat();
});
el.odak.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.ctrlKey) { e.preventDefault(); ozetle(); } });
el.durdur.addEventListener("click", () => { if (durum.iptal) durum.iptal.abort(); });

el.kisiselGonder.addEventListener("click", () => { durum.onay.yineDe = true; ozetle(); });
el.kisiselVazgec.addEventListener("click", () => { el.uyariKisisel.hidden = true; bosDurum("Gönderilmedi."); });
el.butceDevam.addEventListener("click", () => { durum.onay.istekSiniri = Number(el.butceDevam.dataset.gereken); ozetle(); });
el.butceVazgec.addEventListener("click", () => { el.uyariButce.hidden = true; bosDurum("Gönderilmedi."); });
// Seçenek değişirse gereken istek sayısı da değişebilir: önceki bütçe onayı geçersiz olur
for (const g of document.querySelectorAll('input[name="ocr"], input[name="ses"], input[name="uzunluk"]')) {
  g.addEventListener("change", () => { durum.onay.istekSiniri = null; });
}

el.sekmeOzet.addEventListener("click", () => sekmeSec("ozet"));
el.sekmeKaynak.addEventListener("click", () => sekmeSec("kaynak"));
for (const sekme of [el.sekmeOzet, el.sekmeKaynak]) {
  sekme.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const hedef = sekme === el.sekmeOzet ? el.sekmeKaynak : el.sekmeOzet;
    if (hedef.disabled) return;
    hedef.click(); hedef.focus();
  });
}

el.kopyala.addEventListener("click", async () => {
  const metin = el.panelKaynak.hidden ? durum.gorunen.sonuc.ozet : durum.gorunen.kaynak;
  try {
    await navigator.clipboard.writeText(metin);
    el.kopyala.textContent = "Kopyalandı";
  } catch (_) {
    el.kopyala.textContent = "Kopyalanamadı";
  }
  setTimeout(() => { el.kopyala.textContent = "Kopyala"; }, 1600);
});
el.indir.addEventListener("click", (e) => {
  e.stopPropagation();
  const acik = el.indirMenu.hidden;
  el.indirMenu.hidden = !acik;
  el.indir.setAttribute("aria-expanded", String(acik));
  if (acik) el.indirMenu.querySelector("button").focus();
});
for (const b of el.indirMenu.querySelectorAll("button")) b.addEventListener("click", () => indir(b.dataset.bicim));
document.addEventListener("click", (e) => { if (!el.indirMenu.hidden && !e.target.closest(".indir")) menuyuKapat(); });

el.model.addEventListener("change", () => {
  try { localStorage.setItem(MODEL_ANAHTARI, el.model.value); } catch (_) { /* önemli değil */ }
});

durumuYukle();
