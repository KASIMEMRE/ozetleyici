# Türkçe Belge Özetleyici

Bir PDF veya metin dosyasını LLM ile özetleyip sonucu JSON olarak kaydeden komut satırı aracı.
Gemini, Claude, OpenAI ve yerel Ollama ile aynı kodla çalışır: sağlayıcıyı `.env` dosyasından seçersin.

```
python -m ozetleyici ornekler/ornek_belge.txt --uzunluk kisa
```

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

`Activate.ps1` "running scripts is disabled" hatası verirse bir kez şunu çalıştır:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

macOS/Linux'ta etkinleştirme: `source .venv/bin/activate`, kopyalama: `cp .env.example .env`

## Kullanım

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
| `--temperature` (0-2), `--top-p` (0.01-1) | Örnekleme ayarları; verilmezse API'ye gönderilmez |
| `--max-token` | Cevaptaki en fazla token (varsayılan 1024). Düşünen modellerde (ör. Claude) 4096 önerilir |
| `--akissiz` | Akış (streaming) yerine tek seferde cevap |
| `--yine-de-gonder` | Belgede kişisel veri ipucu olsa bile gönder (aşağıya bak) |
| `-s, --sessiz` | Bilgi mesajlarını gizle |

Çıkış kodları: `0` başarılı, `1` hata, `2` geçersiz argüman, `3` kişisel veri nedeniyle durduruldu, `130` Ctrl+C.

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

1. `okuyucu.py` dosyayı okur: PDF için `pypdf`, metin için önce UTF-8, olmazsa Windows Türkçe kodlaması (cp1254).
2. `gizlilik.py` metinde kişisel veri ipucu arar.
3. Metin ~12.000 karakterden uzunsa paragraf sınırlarından parçalanır; her parçadan **ayrıntılı not**
   çıkarılır, sonra notlar istenen uzunlukta tek özete birleştirilir (map-reduce).
4. `llm.py` OpenAI uyumlu API'ye istek atar:
   - 429, 5xx ve bağlantı hatalarında üstel geri çekilmeyle 4 kez dener; `LLM_YEDEK_MODEL` verilmişse sonra onu dener.
   - 400/401/403/404'te hemen sağlayıcının açıklamasıyla hata verir.
   - Token sınırında kesilen, boş veya filtrelenen cevabı kabul etmez.
   - Akış yarıda koparsa ekrandaki yarım metnin geçersiz olduğunu söyleyip baştan alır.
5. `cikti.py` sonucu token ve maliyet bilgisiyle UTF-8 JSON olarak yazar.

## Testler

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Testler internet ve API anahtarı gerektirmez; LLM çağrıları sahte bir HTTP sunucusuyla sınanır.
Gerçek sağlayıcıyla tek bir deneme (küçük bir maliyeti olabilir):

```powershell
$env:OZETLEYICI_GERCEK_TEST=1; python -m pytest -m gercek_api
```

## Ölçümler

Örnek belgede (1.166 karakter, Gemini `gemini-3.5-flash-lite`): 459 girdi token'ı, yani Türkçe metinde
**1 token ≈ 2,5 karakter**. İngilizce için sık verilen "1 token ≈ 4 karakter" kuralından belirgin şekilde
pahalı; Türkçe eklerin etkisi.

## Bilinen sınırlar

- Taranmış (görüntü) PDF'lerden metin çıkmaz; OCR yok.
- Kişisel veri kontrolü isim, adres ve plaka gibi verileri yakalamaz.
- Gemini dışındaki sağlayıcılar yalnızca sahte sunucuyla test edildi.
- Yedek model kullanıldığında maliyet, ana modelin fiyatıyla yaklaşık hesaplanır.
