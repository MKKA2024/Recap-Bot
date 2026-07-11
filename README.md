# Recap-Bot

ဒီ project က Telegram Bot တစ်ခုဖြစ်ပြီး user က video ပို့လိုက်တာနဲ့ အဲဒီ video ထဲက Myanmar (Burmese) background voice ကို text transcript အဖြစ် ပြန်ထုတ်ပေးနိုင်ပါတယ်။ `TTS_ENABLED=true` ထားမယ်ဆိုရင် transcript ကို Myanmar voice အဖြစ် ပြန်ပြီး voice message နဲ့လည်း ပို့ပေးနိုင်ပါတယ်။

## လုပ်ဆောင်ပုံ

1. User က `video`, `video_note` သို့မဟုတ် video file `document` ပို့မယ်
2. Bot က video ကို download လုပ်မယ်
3. `ffmpeg` နဲ့ audio ထုတ်ယူမယ်
4. `whisper` နဲ့ `language="my"` သုံးပြီး speech-to-text ပြောင်းမယ်
5. Transcript ကို Telegram message အဖြစ် ပြန်ပို့မယ်
6. `TTS_ENABLED=true` ဆိုရင် `edge-tts` နဲ့ voice reply ပါ ပြန်ပို့မယ်

## လိုအပ်တဲ့အရာများ

- Python 3.11+
- FFmpeg
- Telegram `API_ID`, `API_HASH`
- `BOT_TOKEN` (BotFather မှ ရယူရန်)

## Telegram API_ID / API_HASH ရယူနည်း

1. [https://my.telegram.org](https://my.telegram.org) ကိုဝင်ပါ
2. သင့် Telegram account နဲ့ login ဝင်ပါ
3. **API development tools** ကိုနှိပ်ပါ
4. App တစ်ခု create လုပ်ပြီး `API_ID` နဲ့ `API_HASH` ကိုယူပါ
5. BotFather ကနေ `BOT_TOKEN` ကိုထုတ်ယူပါ

## FFmpeg install လုပ်နည်း

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### macOS (Homebrew)

```bash
brew install ffmpeg
```

### Windows

- FFmpeg official build ကို download လုပ်ပါ
- `ffmpeg.exe` ကို `PATH` ထဲထည့်ပါ

## Setup

```bash
git clone https://github.com/MKKA2024/Recap-Bot.git
cd Recap-Bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` file ထဲမှာ value တွေဖြည့်ပါ:

```env
API_ID=1234567
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
WHISPER_MODEL=base
TTS_ENABLED=true
```

## Bot run လုပ်နည်း

```bash
python bot.py
```

Bot commands:

- `/start` — welcome message
- `/help` — usage guide
- `/model` — currently used Whisper model

## Whisper model size များ

- `tiny` — အမြန်ဆုံး၊ accuracy နည်းနိုင်
- `base` — speed နဲ့ accuracy balance ကောင်း
- `small` — accuracy ပိုကောင်း
- `medium` — memory ပိုလို၊ quality ပိုကောင်း
- `large` — accuracy အကောင်းဆုံး၊ CPU/RAM ပိုလို

## Docker နဲ့ run လုပ်နည်း

```bash
docker build -t recap-bot .
docker run --env-file .env recap-bot
```

## အသုံးဝင်တဲ့မှတ်ချက်

- Telegram MTProto credentials (`API_ID`, `API_HASH`) သုံးထားလို့ Pyrogram နဲ့ 2GB အထိ media ကို handle လုပ်နိုင်ပါတယ်
- Temporary files တွေကို `tempfile` နဲ့ create လုပ်ပြီး auto cleanup လုပ်ထားပါတယ်
- `document` type ဖြစ်ရင် video file ဟုတ်/မဟုတ် စစ်ပြီးမှ processing ဆက်လုပ်ပါတယ်
