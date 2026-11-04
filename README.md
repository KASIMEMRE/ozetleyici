# Türkçe Belge Özetleyici

Bir PDF veya metin dosyasını LLM ile özetleyip sonucu JSON olarak kaydeden komut satırı aracı.
Gemini, Claude, OpenAI ve yerel Ollama ile aynı kodla çalışır: sağlayıcıyı `.env` dosyasından seçersin.

```
python -m ozetleyici ornekler/ornek_belge.txt --uzunluk kisa
```

## Kurulum (Windows, PowerShell)

Python 3.10 veya üstü gerekir: `python --version`

```powershell
git clone https://github.com/<kullanici-adin>/ozetleyici.git
cd ozetleyici

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
notepad .env      # anahtarını, adresi ve modeli yaz
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
| `--temperature`, `--top-p` | Örnekleme ayarları; verilmezse API'ye gönderilmez |
| `--max-token` | Cevaptaki en fazla token (varsayılan 1024) |
| `--akissiz` | Akış (streaming) yerine tek seferde cevap |

## Çıktı örneği

```json
{
  "kaynak_dosya": "ornek_belge.txt",
  "olusturulma": "2026-11-04T12:30:00+00:00",
  "arac_surumu": "0.1.0",
  "ozet": "…",
  "model": "gemini-3.8-flash",
  "parca_sayisi": 1,
  "istek_sayisi": 1,
  "girdi_token": 512,
  "cikti_token": 140,
  "maliyet_usd": 0.000504,
  "sure_sn": 2.31
}
```

`maliyet_usd` yalnızca `.env`'de `LLM_GIRDI_FIYATI` ve `LLM_CIKTI_FIYATI` verilirse hesaplanır.

## Nasıl çalışır

1. `okuyucu.py` dosyayı okur: PDF için `pypdf`, metin için önce UTF-8, olmazsa Windows Türkçe kodlaması (cp1254).
2. Metin ~12.000 karakterden uzunsa paragraf sınırlarından parçalanır; her parça ayrı özetlenir, sonra özetler birleştirilir.
3. `llm.py` OpenAI uyumlu API'ye istek atar. 429 (hız limiti), 5xx ve bağlantı hatalarında üstel geri çekilmeyle 4 kez dener; 401/404/400'de hemen anlamlı hata verir.
4. `cikti.py` sonucu, token ve maliyet bilgisiyle UTF-8 JSON olarak yazar.

## Testler

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Testler internet ve API anahtarı gerektirmez; LLM çağrıları sahte bir HTTP sunucusuyla sınanır.

## Bilinen sınırlar

- Taranmış (görüntü) PDF'lerden metin çıkmaz; OCR yok.
- Token sayısını bazı sağlayıcılar akış modunda bildirmeyebilir; o zaman JSON'da `null` görünür.
