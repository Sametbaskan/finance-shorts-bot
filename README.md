# Finance Shorts Bot

Her gün otomatik olarak İngilizce kişisel finans Shorts videosu üretir ve Telegram'dan telefonuna yollar.
Tamamen ücretsiz: Gemini (senaryo) + edge-tts (ses) + Pexels (görüntü) + ffmpeg (kurgu) + GitHub Actions (sunucu).

## Kurulum (sadece telefonla, ~15 dk)

### 1) Anahtarları al
| Ne | Nereden | Not |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → "Get API key" | Ücretsiz |
| `PEXELS_API_KEY` | pexels.com/api → hesap aç → "Your API Key" | Ücretsiz |
| `TELEGRAM_BOT_TOKEN` | Telegram'da **@BotFather** → `/newbot` | Token'ı kopyala |

Botu oluşturduktan sonra **kendi botuna Telegram'dan "merhaba" yaz** (yoksa sana mesaj atamaz).
`TELEGRAM_CHAT_ID` isteğe bağlı: boş bırakırsan bot onu kendisi bulur.

### 2) GitHub'a yükle
1. github.com → **New repository** → ad: `finance-shorts-bot` → **Public** seç (Actions sınırsız ücretsiz olur) → Create.
2. **Add file → Upload files** → zip'ten çıkan `bot/main.py`, `requirements.txt`, `README.md`, `history.json` dosyalarını yükle.
   - `bot/main.py` için: **Add file → Create new file**, isim kutusuna `bot/main.py` yaz, içeriği yapıştır.
3. Workflow için: **Add file → Create new file** → isim kutusuna `.github/workflows/shorts.yml` yaz → içeriği yapıştır → Commit.

> Termux biliyorsan: zip'i aç, `git init && git add . && git commit -m ilk && git remote add origin <repo-url> && git push -u origin main`

### 3) Anahtarları gizli olarak ekle
Repo → **Settings → Secrets and variables → Actions → New repository secret**
`GEMINI_API_KEY`, `PEXELS_API_KEY`, `TELEGRAM_BOT_TOKEN` (ve istersen `TELEGRAM_CHAT_ID`) ekle.

### 4) İlk videoyu üret
Repo → **Actions** → "Daily Finance Short" → **Run workflow**. 3-5 dakika içinde video Telegram'a gelir.
Sonra her gün 12:17'de kendiliğinden çalışır.

## Her gün yapacağın şey (1 dk)
1. Telegram'dan videoyu kaydet.
2. YouTube uygulaması → **+ → Short yükle** → videoyu seç.
3. Bot'un yolladığı ikinci mesajdaki başlık / açıklama / hashtag'leri kopyala-yapıştır.
4. İstersen YouTube içinden düşük sesli bir müzik ekle.

## Ayarlar (isteğe bağlı, Settings → Secrets/Variables)
- `VOICE`: ses (varsayılan `en-US-AndrewNeural`; alternatifler: `en-US-ChristopherNeural`, `en-US-AriaNeural`, `en-US-JennyNeural`)
- `VOICE_RATE`: konuşma hızı (varsayılan `+10%`)
- `GEMINI_MODEL`: belirli bir Gemini modeli zorlamak için
- `music/` klasörüne YouTube Ses Kitaplığı'ndan (telifsiz) `.mp3` koyarsan bot arka plana kısık sesle ekler.

Bu üç ayarı kullanmak istersen `.github/workflows/shorts.yml` içindeki `env:` bölümüne de eklemen gerekir.

## Neden otomatik YouTube'a yüklemiyor?
Google'ın denetiminden geçmemiş API projelerinin yüklediği videolar zorunlu olarak "gizli" kalıyor.
Kanal büyüyünce YouTube API denetimine başvurup otomatik yüklemeyi ekleyebiliriz.

## Sorun giderme
- Hata olursa bot Telegram'a hata mesajı yollar; detay: Actions → son çalışma → "Video uret" adımı.
- Telegram'a gelmediyse video yine Actions → son çalışma → **Artifacts** altında durur.
