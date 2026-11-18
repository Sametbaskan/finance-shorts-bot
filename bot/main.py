"""
Finance Shorts Bot
------------------
Her calistiginda:
  1. Gemini (ucretsiz) ile kisisel finans konulu Ingilizce bir Shorts senaryosu yazar
  2. edge-tts (ucretsiz) ile seslendirir, kelime zamanlamalarini alir
  3. Pexels (ucretsiz) ile sahnelere uygun dikey stok videolar indirir
  4. ffmpeg ile 1080x1920 video kurgular, kelime kelime vurgulu altyazi gomer
  5. Videoyu + baslik/aciklamayi Telegram'dan telefonuna yollar

Gerekli ortam degiskenleri (GitHub > Settings > Secrets):
  GEMINI_API_KEY, PEXELS_API_KEY, TELEGRAM_BOT_TOKEN, (istege bagli) TELEGRAM_CHAT_ID
"""

import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
WORK = ROOT / "work"
HISTORY_FILE = ROOT / "history.json"
FONTS_DIR = ROOT / "fonts"
MUSIC_DIR = ROOT / "music"

W, H, FPS = 1080, 1920, 30

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
VOICE = os.getenv("VOICE", "en-US-AndrewNeural")
VOICE_RATE = os.getenv("VOICE_RATE", "+10%")
GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL", "")] if m] + [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]

# ---------------------------------------------------------------- konular
TOPICS = [
    "emergency fund", "compound interest", "credit score basics", "the 50/30/20 budget",
    "index funds", "inflation eating your savings", "subscription creep", "credit card interest",
    "the minimum payment trap", "lifestyle inflation", "pay yourself first", "sinking funds",
    "debt snowball vs debt avalanche", "renting vs buying a home", "car loans",
    "the 24-hour rule for impulse buys", "high-yield savings accounts", "dollar cost averaging",
    "diversification", "hidden fees in investment funds", "starting retirement savings early",
    "building a side income", "negotiating your salary", "opportunity cost",
    "buy now pay later traps", "net worth tracking", "saving money on groceries",
    "the rule of 72", "extended warranties", "why cards make you spend more than cash",
    "bank fees", "automating your savings", "emotional spending", "the true cost of a new car",
    "budgeting on an irregular income", "money habits of wealthy people", "the latte factor debate",
    "paying off debt vs investing", "the power of small raises", "student loan strategies",
    "financial goals that actually work", "the cost of waiting to invest", "frugal vs cheap",
    "how interest works on loans", "avoiding scams that target your money",
    "price anchoring tricks stores use", "the envelope budgeting method", "money and relationships",
    "what to do with a bonus or windfall", "cost per use thinking",
]

ANGLES = [
    "3 common mistakes people make about it",
    "a popular myth vs the actual fact",
    "the simple math behind it, with one concrete example",
    "one easy rule anyone can start today",
    "what happens if you do it for 10 years vs if you don't",
    "comparing two choices side by side",
    "a surprising fact most people don't know",
    "a quick 3-step mini guide",
    "the hidden cost nobody talks about",
    "a short relatable story of two friends making different choices",
]


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Komut basarisiz: {' '.join(map(str, cmd[:6]))}...\n{r.stderr[-2000:]}")
    return r.stdout


def ffprobe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


# ---------------------------------------------------------------- gecmis
def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": [], "titles": [], "pexels_ids": []}


def save_history(h):
    for k in h:
        h[k] = h[k][-300:]
    HISTORY_FILE.write_text(json.dumps(h, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- 1) senaryo
def pick_topic(history):
    recent = set(history["topics"][-len(TOPICS) // 2:])
    choices = [t for t in TOPICS if t not in recent] or TOPICS
    return random.choice(choices), random.choice(ANGLES)


def build_prompt(topic, angle, past_titles):
    past = "\n".join(f"- {t}" for t in past_titles[-40:]) or "- (none yet)"
    return f"""You write scripts for a faceless YouTube Shorts channel about personal finance.
Audience: young adults (18-35) who want to get better with money. Tone: friendly, punchy, clear.

Topic: {topic}
Angle: {angle}

Rules:
- Total narration: 110-140 words (about 45-55 seconds spoken).
- First sentence is a strong hook (a surprising claim, a question, or a bold statement). No "Hey guys", no greetings.
- Short sentences. Plain English. Use one concrete number example where it helps.
- Only state widely accepted, general facts. No specific stock/crypto picks, no promises of returns,
  no country-specific tax limits or current interest rates that could be outdated.
- Do not repeat these previous videos:
{past}
- End with a short line that invites a comment (a question to the viewer).
- Split the narration into 5-8 scenes. Each scene has the narration text and a "visual":
  2-4 simple English words for a stock-video search that matches the scene
  (concrete and filmable, e.g. "counting cash", "woman shopping online", "piggy bank coins").

Return ONLY JSON in exactly this shape:
{{
  "title": "catchy title under 60 characters, no hashtags",
  "scenes": [{{"narration": "...", "visual": "..."}}],
  "description": "2-3 sentence YouTube description",
  "hashtags": ["#personalfinance", "#money", "..."]
}}"""


def call_gemini(prompt):
    last_err = None
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"},
        }
        try:
            r = requests.post(url, params={"key": GEMINI_KEY}, json=body, timeout=90)
            if r.status_code in (404, 400) and "not found" in r.text.lower():
                last_err = f"{model}: model bulunamadi"
                continue
            if r.status_code == 429:
                last_err = f"{model}: kota doldu (429)"
                time.sleep(10)
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            log(f"Gemini modeli: {model}")
            return text
        except Exception as e:
            last_err = f"{model}: {e}"
    raise RuntimeError(f"Gemini cevap vermedi. Son hata: {last_err}")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def generate_script(history):
    topic, angle = pick_topic(history)
    log(f"Konu: {topic} | Aci: {angle}")
    prompt = build_prompt(topic, angle, history["titles"])
    for attempt in range(3):
        try:
            data = parse_json(call_gemini(prompt))
            scenes = [s for s in data["scenes"] if s.get("narration", "").strip()]
            words = sum(len(s["narration"].split()) for s in scenes)
            if not (4 <= len(scenes) <= 10) or not (80 <= words <= 175):
                raise ValueError(f"Kurala uymayan senaryo ({len(scenes)} sahne, {words} kelime)")
            data["scenes"] = scenes
            data["topic"] = topic
            data["title"] = data["title"].strip().strip('"')[:90]
            log(f"Baslik: {data['title']} ({words} kelime)")
            return data
        except Exception as e:
            log(f"Senaryo denemesi {attempt + 1} basarisiz: {e}")
            time.sleep(3)
    raise RuntimeError("Gecerli senaryo uretilemedi")


# ---------------------------------------------------------------- 2) seslendirme
async def _tts(text, mp3_path):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE, boundary="WordBoundary")
    except TypeError:  # eski edge-tts surumu
        comm = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE)
    words, sentences = [], []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            t = chunk["type"]
            if t == "audio":
                f.write(chunk["data"])
            elif t in ("WordBoundary", "SentenceBoundary"):
                item = {
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                }
                (words if t == "WordBoundary" else sentences).append(item)
    if not words and sentences:  # sadece cumle zamani geldiyse kelimelere bol
        for s in sentences:
            toks = s["text"].split()
            total = sum(len(x) for x in toks) or 1
            cur = s["start"]
            for tok in toks:
                d = (s["end"] - s["start"]) * len(tok) / total
                words.append({"text": tok, "start": cur, "end": cur + d})
                cur += d
    return words


def make_voice(text, mp3_path):
    for attempt in range(3):
        try:
            words = asyncio.run(_tts(text, mp3_path))
            if words:
                return words
            raise RuntimeError("Kelime zamanlamasi gelmedi")
        except Exception as e:
            log(f"TTS denemesi {attempt + 1} basarisiz: {e}")
            time.sleep(5)
    raise RuntimeError("Seslendirme yapilamadi")


# ---------------------------------------------------------------- 3) stok video
def pexels_search(query, used_ids):
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={"query": query, "orientation": "portrait", "per_page": 20, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    vids = r.json().get("videos", [])
    fresh = [v for v in vids if v["id"] not in used_ids] or vids
    random.shuffle(fresh)
    for v in fresh:
        files = [f for f in v.get("video_files", [])
                 if f.get("width") and f.get("height") and f["height"] > f["width"]
                 and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
        if files:
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            return v["id"], best["link"]
    return None, None


def download(url, path):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for part in r.iter_content(1 << 20):
                f.write(part)


def fetch_clips(scenes, history):
    used = set(history["pexels_ids"])
    clips = []
    fallbacks = ["money", "saving money", "wallet", "city life", "shopping", "laptop work"]
    for i, sc in enumerate(scenes):
        vid = link = None
        for q in [sc["visual"], " ".join(sc["visual"].split()[:2]), random.choice(fallbacks)]:
            vid, link = pexels_search(q, used)
            if vid:
                break
        if not vid:
            raise RuntimeError(f"Sahne {i + 1} icin video bulunamadi")
        path = WORK / f"clip_{i}.mp4"
        download(link, path)
        used.add(vid)
        history["pexels_ids"].append(vid)
        clips.append(path)
        log(f"Sahne {i + 1}: '{sc['visual']}' -> pexels #{vid}")
    return clips


# ---------------------------------------------------------------- 4) zamanlama + altyazi
def scene_times(scenes, words, total):
    counts = [len(s["narration"].split()) for s in scenes]
    total_words = sum(counts)
    n = len(words)
    starts, cum = [0.0], 0
    for c in counts[:-1]:
        cum += c
        idx = min(n - 1, round(cum / total_words * n))
        starts.append(words[idx]["start"])
    ends = starts[1:] + [total]
    return [(s, max(0.8, e - s)) for s, e in zip(starts, ends)]


def ass_time(t):
    t = max(0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def chunk_words(words, max_words=3, max_chars=16):
    chunks, cur = [], []
    for i, w in enumerate(words):
        if cur:
            gap = w["start"] - cur[-1]["end"]
            chars = sum(len(x["text"]) for x in cur) + len(w["text"])
            if len(cur) >= max_words or chars > max_chars or gap > 0.25 \
                    or re.search(r"[.!?,;:]$", cur[-1]["text"]):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words, title, total, font, bold, path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,{bold},0,0,0,100,100,2,0,1,8,4,5,70,70,0,1
Style: Title,{font},76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00101010,{bold},0,0,0,100,100,1,0,3,18,0,8,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    # Baslik karti: ilk 2.8 saniye ustte
    lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(2.8, total))},Title,,0,0,0,,"
                 f"{{\\an8\\pos({W // 2},300)\\fad(150,250)}}{ass_escape(title.upper())}")
    HL = "&H0000D7FF&"  # sari (ASS renkleri BGR)
    chunks = chunk_words(words)
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        chunk_end = min(nxt, ch[-1]["end"] + 0.6)
        for wi, w in enumerate(ch):
            st = w["start"]
            en = ch[wi + 1]["start"] if wi + 1 < len(ch) else chunk_end
            if en <= st:
                continue
            parts = []
            for wj, x in enumerate(ch):
                txt = ass_escape(x["text"].upper())
                parts.append(f"{{\\c{HL}}}{txt}{{\\c&H00FFFFFF&}}" if wj == wi else txt)
            pop = "\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Cap,,0,0,0,,"
                         f"{{\\an5\\pos({W // 2},{int(H * 0.64)}){pop}}}{' '.join(parts)}")
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 5) kurgu
def pick_font():
    if FONTS_DIR.exists() and any(FONTS_DIR.glob("Anton*.ttf")):
        return "Anton", 0
    return os.getenv("FALLBACK_FONT", "DejaVu Sans"), -1


def render(clips, times, voice_mp3, ass_path, out_path):
    segs = []
    for i, (clip, (_, dur)) in enumerate(zip(clips, times)):
        seg = WORK / f"seg_{i}.mp4"
        # hafif yatay kaydirma ile her sahne canli dursun
        zoom = f"scale={W * 1.08:.0f}:{H * 1.08:.0f}:force_original_aspect_ratio=increase," \
               f"crop={W}:{H}:(iw-{W})*t/{dur:.2f}*0.5:(ih-{H})/2"
        run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(clip), "-t", f"{dur:.3f}",
             "-vf", f"{zoom},setsar=1,fps={FPS},format=yuv420p",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", str(seg)])
        segs.append(seg)
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))
    joined = WORK / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    ass_arg = ass_path.as_posix().replace(":", r"\:")
    vf = f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill,ass='{ass_arg}'"
    if FONTS_DIR.exists():
        vf += f":fontsdir='{FONTS_DIR.as_posix()}'"

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-i", str(voice_mp3)]
    music = sorted(MUSIC_DIR.glob("*.mp3")) if MUSIC_DIR.exists() else []
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(music))]
        afilter = "[2:a]volume=0.07[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]"
        cmd += ["-filter_complex", f"[0:v]{vf}[v];{afilter}", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out_path)]
    run(cmd)


# ---------------------------------------------------------------- 6) telegram
def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", timeout=180, **kw)
    if not r.ok:
        log(f"Telegram {method} hatasi: {r.text[:300]}")
    return r


def tg_chat_id():
    if TG_CHAT:
        return TG_CHAT
    r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", timeout=30).json()
    for upd in reversed(r.get("result", [])):
        msg = upd.get("message") or upd.get("channel_post")
        if msg:
            return str(msg["chat"]["id"])
    return ""


def send_telegram(video, meta):
    if not TG_TOKEN:
        log("Telegram ayarlanmamis, video sadece GitHub'da 'Artifacts' altinda.")
        return
    chat = tg_chat_id()
    if not chat:
        log("Chat ID bulunamadi. Botuna Telegram'dan bir mesaj at ve tekrar calistir.")
        return
    with open(video, "rb") as f:
        tg("sendVideo", data={"chat_id": chat, "caption": meta["title"][:1000],
                              "supports_streaming": "true", "width": W, "height": H},
           files={"video": (video.name, f, "video/mp4")})
    tg("sendMessage", data={"chat_id": chat, "text": meta_text(meta)[:4000]})


def tg_error(text):
    if TG_TOKEN:
        chat = tg_chat_id()
        if chat:
            tg("sendMessage", data={"chat_id": chat, "text": f"Shorts botu hata verdi:\n{text[:3500]}"})


def meta_text(meta):
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in meta.get("hashtags", [])[:8])
    if "#shorts" not in tags.lower():
        tags = "#shorts " + tags
    return (f"BASLIK:\n{meta['title']}\n\n"
            f"ACIKLAMA:\n{meta['description']}\n\n"
            f"This video is for educational purposes only and is not financial advice. "
            f"Voiceover is AI-generated.\n\n{tags}")


# ---------------------------------------------------------------- ana akis
def main():
    for k, v in {"GEMINI_API_KEY": GEMINI_KEY, "PEXELS_API_KEY": PEXELS_KEY}.items():
        if not v:
            sys.exit(f"Eksik ayar: {k}")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    OUT.mkdir(exist_ok=True)

    history = load_history()
    meta = generate_script(history)
    narration = " ".join(s["narration"].strip() for s in meta["scenes"])

    voice = WORK / "voice.mp3"
    words = make_voice(narration, voice)
    total = ffprobe_duration(voice) + 0.4
    log(f"Ses suresi: {total:.1f} sn, {len(words)} kelime")

    times = scene_times(meta["scenes"], words, total)
    clips = fetch_clips(meta["scenes"], history)

    font, bold = pick_font()
    ass = WORK / "subs.ass"
    build_ass(words, meta["title"], total, font, bold, ass)

    slug = re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")[:50] or "short"
    video = OUT / f"{time.strftime('%Y%m%d')}-{slug}.mp4"
    render(clips, times, voice, ass, video)
    (OUT / "meta.txt").write_text(meta_text(meta), encoding="utf-8")
    log(f"Video hazir: {video.name} ({video.stat().st_size / 1e6:.1f} MB)")

    send_telegram(video, meta)
    history["topics"].append(meta["topic"])
    history["titles"].append(meta["title"])
    save_history(history)
    log("Bitti.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"HATA: {e}")
        try:
            tg_error(str(e))
        finally:
            sys.exit(1)
