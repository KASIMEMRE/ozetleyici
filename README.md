# Türkçe Belge Özetleyici

PDF, Word, Excel, PowerPoint, CSV ve görsel (taranmış) belgeleri LLM ile özetleyen araç.
Tarayıcıda çalışan bir arayüzü ve bir komut satırı aracı var. Gemini, Claude, OpenAI ve yerel
Ollama ile aynı kodla çalışır: sağlayıcıyı `.env` dosyasından seçersin.

```
python -m ozetleyici.web                                   # tarayıcı arayüzü
python -m ozetleyici ornekler/ornek_belge.txt -u kisa      # komut satırı
```

| Tür | Uzantı | Nasıl okunur |
| --- | --- | --- |
| Metin | `.txt` `.md` | UTF-8, olmazsa Windows Türkçe (cp1254) |
| PDF | `.pdf` | Metinli sayfalar doğrudan; taranmış sayfalar OCR ile |
| Word | `.docx` | Başlıklar, paragraflar, tablolar, üst bilgi; **gizli biçimli yazı okunmaz** |
| PowerPoint | `.pptx` | Slayt metinleri, tablolar, konuşmacı notları |
| Excel | `.xlsx` `.xlsm` | Her sayfadan 100 satır önizleme + **istatistikler Python'da, tüm satırlardan**; gizli sayfalar ve makrolar okunmaz |
| CSV | `.csv` | `;` `,` sekme ayırıcısı otomatik; Türkçe ondalık (1.234,56) anlaşılır |
| Görsel | `.png` `.jpg` | OCR ile |
| Ses | `.mp3` `.wav` `.m4a` `.ogg` `.opus` `.flac` | Konuşma yazıya dökülür (yerel Whisper veya model ile), sonra özetlenir |
| Video | `.mp4` `.mov` `.mkv` `.webm` `.avi` | Yalnızca ses kanalı; görüntüdeki yazı ve slaytlar okunmaz |

Eski `.doc` `.xls` `.ppt` biçimleri desteklenmez; Office'te "Farklı Kaydet" ile yeni biçime çevir.
Boyut sınırı belgeler için 25 MB (komut satırında 50 MB), ses ve video için 200 MB ve en fazla 60 dakika.

## Kurulum (Windows, PowerShell)

Python 3.10 veya üstü gerekir: `python --version`

```powershell
git clone https://github.com/KASIMEMRE/ozetleyici.git
cd ozetleyici

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
notepad .env      # anahtarı SADECE bu dosyaya yaz

git config core.hooksPath .githooks   # commit'lere anahtar girmesini engelleyen kancayı aç
```

### Tesseract (taranmış belgeleri yerel okumak için, isteğe bağlı)

1. [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) sayfasından Windows kurucusunu indir.
2. Kurulumda **Additional language data** altından **Turkish**'i işaretle.
3. Varsayılan yere (`C:\Program Files\Tesseract-OCR`) kurduysan başka ayar gerekmez; farklı bir yere kurduysan
   `.env` dosyasına `TESSERACT_YOLU=` ile `tesseract.exe`'nin tam yolunu yaz.

### Konuşma tanıma modeli (ses ve video için)

`pip install -r requirements.txt` ile faster-whisper kurulur. Model ilk ses dosyasında bir kez internetten indirilir
(`small` ≈ 500 MB) ve sonra internetsiz çalışır. İşlemcide çalıştığı için yavaştır: 10 dakikalık bir kayıt birkaç
dakika sürebilir. Modeli `.env`'de `WHISPER_MODELI` ile değiştirebilirsin (`medium` Türkçede daha doğru, ~2-3 kat yavaş).

Tesseract kurulu değilse taranmış sayfalar için "Model ile okuma" seçeneğini veya `--ocr gemini`'yi kullanabilirsin.

`Activate.ps1` "running scripts is disabled" hatası verirse bir kez şunu çalıştır:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

macOS/Linux'ta etkinleştirme: `source .venv/bin/activate`, kopyalama: `cp .env.example .env`

## Web arayüzü

```powershell
python -m ozetleyici.web
```

Tarayıcı kendiliğinden `http://127.0.0.1:8765` adresini açar. Arayüzde:

- Dosyayı sayfanın herhangi bir yerine bırakabilir, **Ctrl + Enter** ile özetleyebilirsin.
- Yalnızca o dosya türünde anlamı olan ayarlar görünür (OCR yalnızca PDF ve görselde, yazıya dökme yalnızca ses ve videoda).
- **Neye odaklansın?** alanına "yaptırımlar ve süreler" gibi bir istek yazabilirsin; bu yalnızca vurguyu değiştirir,
  modelin belgeye sadık kalma kurallarını geçersiz kılamaz.
- **Kaynak metin** sekmesi modelin gördüğü metni gösterir; ses ve videoda bu, yazıya dökülmüş konuşmadır.
- **Veri izi**, neyin bu bilgisayarda kaldığını ve neyin modele gittiğini (kaç karakter, kaç görüntü veya ses parçası) gösterir.
- Uzun işlerde aşama, geçen süre ve **Durdur** düğmesi görünür; durdurunca sıradaki istek gönderilmez.
- **Sorular** sekmesinde özetlenen belgeye soru sorabilirsin (aşağıya bak).
- Özeti Markdown, düz metin veya JSON olarak indirebilirsin. **Bu oturumda** listesi önceki özetlere döner;
  yalnızca bellekte tutulur, sayfayı kapatınca silinir.
 Sağ üstten modeli seçebilirsin: liste,
anahtarının erişebildiği ve metin üreten modellerden oluşur (ses/görsel üretme ve embedding modelleri elenir).
Seçimin tarayıcıda hatırlanır. Dosyayı sürükle-bırak, uzunluğu ve taranmış
sayfaların nasıl okunacağını seç, **Özetle**'ye bas. Özet yazıldıkça görünür; bitince kopyalayabilir veya
JSON olarak indirebilirsin. Durdurmak için terminalde Ctrl+C.

## Belgeye soru sorma

Özet bittikten sonra **Sorular** sekmesinde belgeyle ilgili soru sorabilirsin. Cevap yalnızca belgeden gelir ve
her bilginin yanında kaynak numarası bulunur (`[1]`); numaraya tıklayınca ilgili parça **Kaynak metin**
sekmesinde vurgulanır. Belgede cevap yoksa "Belgede bu sorunun cevabını bulamadım." der.

Nasıl çalışır (RAG, getirme destekli üretim):

1. Belge, sayfa/slayt/zaman bilgisi korunarak ~1.000 karakterlik, birbirine biraz taşan parçalara bölünür.
   Parçalar sayfa ve slayt sınırını aşmaz; ses dökümünde parçanın zaman aralığı gösterilir.
2. İlk soruda parçalar embedding vektörüne çevrilir (100'erli gruplar, her grup bir istek); sonraki sorularda
   yalnızca sorunun kendisi çevrilir.
3. **Hibrit arama:** anlam benzerliği (vektörler) ile kelime eşleşmesi (BM25, Türkçe için kaba kök: ilk 5 harf)
   birleştirilir; tutar, tarih ve isim gibi tam eşleşmeler kaçmaz. En iyi 5 parça modele verilir.
4. Sağlayıcı embedding sunmuyorsa ya da kota yoksa arama kelime eşleşmesiyle devam eder ve bu not olarak gösterilir.

Belgeler yalnızca bellekte tutulur (en fazla 5 belge, 1 saat); sunucu kapanınca silinir. Tek belgede birkaç yüz
parça olduğu için ayrı bir vektör veritabanı kullanılmaz; numpy ile bellekte aranır. Soru da istek sınırına tabidir:
ilk soru "parça sayısı / 100 + 2", sonrakiler 2 istek harcar.

## Komut satırı

```powershell
python -m ozetleyici belge.pdf                       # orta uzunlukta özet, belge.ozet.json
python -m ozetleyici belge.pdf -u kisa -o ozet.json  # kısa özet, çıktı yolu seçili
python -m ozetleyici belge.txt --temperature 0.2     # örnekleme ayarı ile
python -m ozetleyici belge.pdf --akissiz             # cevabı tek seferde al
python -m ozetleyici --help                          # tüm seçenekler
```

| Seçenek | Açıklama |
| --- | --- |
| `-u, --uzunluk` | `kisa`, `orta` (varsayılan), `uzun` |
| `-o, --cikti` | JSON dosyasının yolu |
| `--model` | `.env`'deki modeli bu çalıştırma için değiştirir |
| `--odak` | Özet neye ağırlık versin (ör. `--odak "teslim tarihleri"`) |
| `--modelleri-listele` | Anahtarının erişebildiği özet modellerini listeler |
| `--temperature` (0-2), `--top-p` (0.01-1) | Örnekleme ayarları; verilmezse API'ye gönderilmez |
| `--max-token` | Cevaptaki en fazla token (varsayılan 1024). Düşünen modellerde (ör. Claude) 4096 önerilir |
| `--akissiz` | Akış (streaming) yerine tek seferde cevap |
| `--ses` | `yerel` (Whisper, varsayılan, ses bilgisayardan çıkmaz), `gemini` (ses sağlayıcıya gider) |
| `--whisper-modeli` | `tiny` `base` `small` `medium` `large-v3` `turbo` |
| `--istek-siniri` | Bu belge için en fazla API isteği (varsayılan 20) |
| `--ocr` | `yerel` (Tesseract, varsayılan), `gemini` (görüntü sağlayıcıya gider), `kapali` |
| `--yine-de-gonder` | Belgede kişisel veri ipucu olsa bile gönder (aşağıya bak) |
| `-s, --sessiz` | Bilgi mesajlarını gizle |

Çıkış kodları: `0` başarılı, `1` hata, `2` geçersiz argüman, `3` kişisel veri nedeniyle durduruldu,
`4` istek sınırı nedeniyle durduruldu, `130` Ctrl+C.

## Maliyet kontrolü

Uygulama yalnızca **Özetle**'ye basınca LLM sağlayıcısına istek atar; arka planda hiçbir şey çalışmaz.
Kısa bir belge 1 istek, uzun bir belge "parça sayısı + 1" istek, model ile OCR her taranmış sayfa için 1,
model ile ses her 5 dakika için 1 istek harcar. Korumalar:

- **Belge başına istek sınırı** (varsayılan 20, `LLM_EN_FAZLA_ISTEK`): iş başlamadan önce gereken istek sayısı
  hesaplanır; sınırı aşıyorsa hiçbir istek gönderilmeden onay istenir. Tahmin yanlış çıksa bile sınır aşılamaz,
  çünkü her istekten önce ayrıca sayılır. Hata sonrası yeniden denemeler sayılmaz (sağlayıcı başarısız isteği
  ücretlendirmez).
- **Sekmeyi kapatınca iş durur**: bir sonraki istek gönderilmez, süren akış kesilir.
- **Gerçek maliyet**: `maliyet_usd`, OCR ve ses okumaya harcanan token'ları da içerir.

**Model seçimi.** Google, hangi modelin ücretsiz katmanda açık olduğunu bir API ile bildirmiyor; kendi
hesabının limitlerini [AI Studio'daki limitler sayfasında](https://aistudio.google.com/rate-limit) görebilirsin.
Faturalandırma bağlı değilse kapalı bir model seçmek para harcatmaz: istek reddedilir ve uygulama
"kota 0 / ücretsiz katmanda kapalı olabilir" der (boşuna yeniden denemez; günlük kota dolduğunda da hemen söyler).
`.env`'deki fiyatlar yalnızca varsayılan model içindir; başka model seçilince maliyet "hesaplanmadı" görünür.

Gemini'nin ücretsiz katmanında ücret alınmaz; sınıra gelince istekler reddedilir. Ücretli katmana geçersen
Google AI Studio'da **Spend** sayfasından harcama tavanı koy.

## Gizlilik ve güvenlik

**Belgen sağlayıcıya gider.** Özetlemek için belgenin metni LLM sağlayıcısının sunucusuna gönderilir.
Google'ın Gemini API koşullarına göre ücretsiz katmanda gönderilen içerik ürün ve model geliştirmede
kullanılabilir ve insan değerlendiriciler tarafından okunabilir; Google ücretsiz katmana hassas, gizli veya
kişisel bilgi gönderilmemesini istiyor ([Gemini API ek koşulları](https://ai.google.dev/gemini/terms)).
Kişisel veya gizli belgeler için ücretli katman ya da verinin bilgisayardan çıkmadığı Ollama kullan.

**Kişisel veri ön kontrolü.** Program göndermeden önce metinde T.C. kimlik no (kontrol haneleriyle),
IBAN, e-posta ve cep telefonu arar; bulursa **göndermeden durur** (çıkış kodu 3). Bilerek göndermek için
`--yine-de-gonder` kullan. Bu kaba bir ön elemedir: isim ve adres gibi verileri yakalamaz, maskeleme yapmaz.

**Anahtarın korunması.**

- Anahtar yalnızca `.env` dosyasında durur; `.env`, `.env.local` vb. `.gitignore`'dadır.
- `git config core.hooksPath .githooks` ile açılan kanca, her commit'ten önce `scripts/gizli_tara.py`
  ile commit'e girecek içeriği tarar; anahtar veya `.env` dosyası görürse commit'i durdurur.
- GitHub Actions her gönderimde aynı taramayı ve testleri Windows ve Linux'ta çalıştırır.
- Hata mesajlarında anahtar görünürse `***` ile gizlenir; JSON çıktısına anahtar, belgenin tam metni
  veya dosyanın tam yolu yazılmaz. Özet dosyaları (`*.ozet.json`) da `.gitignore`'dadır, çünkü
  belgedeki bilgileri içerebilir.

**Web arayüzü.**

- Yalnızca `127.0.0.1` adresinde dinler; aynı ağdaki başka bilgisayarlar erişemez. Uygulamada kullanıcı girişi
  olmadığı için bu bilinçli bir karar: ağa açılsa başkası senin API anahtarınla özet yaptırabilirdi.
- Her açılışta rastgele bir oturum anahtarı üretilir; API bu anahtar olmadan çalışmaz. Böylece açık olan başka
  bir web sitesi tarayıcın üzerinden uygulamaya istek gönderemez (CSRF). `Host` başlığı da denetlenir
  (DNS rebinding'e karşı).
- Sıkı Content-Security-Policy; sayfada yalnızca uygulamanın kendi betiği çalışır. Belgeden veya modelden gelen
  metin sayfaya HTML olarak değil düz metin olarak yazılır (XSS'e karşı).
- Yüklenen dosya **diske yazılmaz**, yalnızca bellekte işlenir; en fazla 25 MB. Aynı anda tek belge işlenir.

**Kötü niyetli dosyalara karşı.**

- Dosyanın gerçek türü ilk baytlarından denetlenir; `.pdf` uzantılı bir zip reddedilir.
- Word, Excel ve PowerPoint aslında zip arşividir; açıldığında 200 MB'ı aşan veya aşırı sıkıştırılmış dosyalar
  (zip bombası) ve şüpheli iç yollar reddedilir. Excel XML'i `defusedxml` ile güvenli ayrıştırılır.
- 40 milyon pikselden büyük görseller (piksel bombası) reddedilir; OCR en fazla 30 sayfa yapar.
- Görünmez Unicode karakterler (sıfır genişlikli boşluk, yön değiştirme işaretleri), Word'deki gizli yazılar ve
  Excel'deki gizli sayfalar modele gönderilmez: bunlar belgeye okurun göremeyeceği talimat saklamanın yollarıdır.
- Excel makroları hiçbir zaman yüklenmez veya çalıştırılmaz.

**Ses de kişisel veridir.** Bir ses kaydı konuşanı tanımlar ve konuşmalar genelde isim ve başka kişisel bilgi
içerir. Bu yüzden varsayılan yerel Whisper'dır: ses bilgisayardan çıkmaz. Ses/video çözümleme (ffmpeg) güvenilmeyen
dosyaları ayrıştırdığı için **ayrı bir süreçte** çalışır: süre sınırı (5 dakika), Linux/macOS'ta bellek sınırı, en fazla
60 dakikalık ses (dosya süresini gizlese bile çözülen miktara göre kesilir) ve bu süreç **API anahtarlarını görmez**.
Whisper'ın sessiz bölümlerde uydurduğu bilinen satırlar (ör. "Altyazı M.K.") atılır.

**Model ile OCR'ın bir bedeli var.** Model ile OCR'da ve model ile seste görüntü/ses, kişisel veri kontrolünden
**önce** sağlayıcıya gider (metni ancak okuduktan sonra kontrol edebiliriz). Kişisel veri içerebilecek taramalar
için yerel Tesseract'ı kullan.

**Belgedeki talimatlar.** Belge `<belge>` etiketleri arasında gönderilir ve modele belgedeki talimatları
uygulamaması söylenir. Bu, prompt injection'a karşı yalnızca ilk savunma hattıdır; tam koruma değildir.

## Çıktı örneği

```json
{
  "kaynak_dosya": "ornek_belge.txt",
  "olusturulma": "2026-11-04T14:13:49+00:00",
  "arac_surumu": "0.2.0",
  "ozet": "Örnek Şirket A.Ş.'nin 1 Ocak 2027 tarihinde yürürlüğe girecek…",
  "model": "gemini-3.5-flash-lite",
  "parca_sayisi": 1,
  "istek_sayisi": 1,
  "girdi_token": 459,
  "cikti_token": 173,
  "maliyet_usd": null,
  "sure_sn": 11.77,
  "kullanilan_modeller": ["gemini-3.5-flash-lite"]
}
```

`maliyet_usd` yalnızca `.env`'de `LLM_GIRDI_FIYATI` ve `LLM_CIKTI_FIYATI` verilirse hesaplanır.

## Nasıl çalışır

1. `okuyucular/` paketi dosyayı türüne göre okur (yukarıdaki tablo). Taranmış PDF sayfaları `pypdfium2` ile
   görüntüye çevrilip OCR'a verilir. Excel'de toplam/ortalama gibi hesaplar Python'da yapılır, çünkü LLM'ler
   sayılarla güvenilmezdir.
2. `gizlilik.py` metinde kişisel veri ipucu arar.
3. Metin ~12.000 karakterden uzunsa paragraf sınırlarından parçalanır; her parçadan **ayrıntılı not**
   çıkarılır, sonra notlar istenen uzunlukta tek özete birleştirilir (map-reduce).
4. `llm.py` OpenAI uyumlu API'ye istek atar:
   - 429, 5xx ve bağlantı hatalarında üstel geri çekilmeyle 4 kez dener; `LLM_YEDEK_MODEL` verilmişse sonra onu dener.
   - 400/401/403/404'te hemen sağlayıcının açıklamasıyla hata verir.
   - Token sınırında kesilen, boş veya filtrelenen cevabı kabul etmez.
   - Akış yarıda koparsa ekrandaki yarım metnin geçersiz olduğunu söyleyip baştan alır.
5. `cikti.py` sonucu token ve maliyet bilgisiyle UTF-8 JSON olarak yazar.
6. `web/` aynı çekirdeği FastAPI ile sunar; özet satır satır JSON olayları (NDJSON) olarak tarayıcıya akar.

## Testler

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Testler internet ve API anahtarı gerektirmez; LLM çağrıları sahte bir HTTP sunucusuyla sınanır.
Gerçek sağlayıcıyla tek bir deneme (küçük bir maliyeti olabilir):

```powershell
$env:OZETLEYICI_GERCEK_TEST=1; python -m pytest -m gercek_api -k saglayici
```

Gerçek Whisper modeliyle Türkçe deneme: Ses Kaydedicisi ile şu cümleyi kaydet:
"Bugünkü toplantıda bütçe onaylandı ve proje teslim tarihi mart ayına ertelendi." Sonra:

```powershell
$env:OZETLEYICI_SES_DOSYASI="C:\Users\Emre\Documents\Ses Kayıtları\kayit.m4a"
python -m pytest -m gercek_api -k whisper -s
```

Test, modelin çıktısını ve cümledeki 6 anahtar kelimeden kaçını doğru yazdığını gösterir.

## Ölçümler

Örnek belgede (1.166 karakter, Gemini `gemini-3.5-flash-lite`): 459 girdi token'ı, yani Türkçe metinde
**1 token ≈ 2,5 karakter**. İngilizce için sık verilen "1 token ≈ 4 karakter" kuralından belirgin şekilde
pahalı; Türkçe eklerin etkisi.

## Bilinen sınırlar

- OCR kalitesi taramanın kalitesine bağlıdır; model ile OCR'da model okuyamadığı yeri tahmin edebilir.
- Videoda yalnızca konuşma okunur; ekrandaki slayt ve yazılar özetlenmez.
- Konuşmacılar yerel Whisper'da ayrılmaz (kimin konuştuğu belirtilmez); model ile yazıya dökmede denenir.
- Excel'de formül sonuçları dosyada kayıtlı değilse (dosya Excel'de hiç açılıp kaydedilmediyse) hücreler boş görünür.
- Kişisel veri kontrolü isim, adres ve plaka gibi verileri yakalamaz.
- Gemini dışındaki sağlayıcılar yalnızca sahte sunucuyla test edildi.
- Yedek model kullanıldığında maliyet, ana modelin fiyatıyla yaklaşık hesaplanır.
