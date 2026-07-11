import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Callable

import edge_tts
import ffmpeg
import torch
import whisper
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from config import API_HASH, API_ID, BOT_TOKEN, TTS_ENABLED, WHISPER_MODEL

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger("video-transcriber")

SUPPORTED_VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}
TTS_VOICE = "my-MM-NilarNeural"
PROGRESS_UPDATE_THRESHOLD_PERCENT = 10
PROGRESS_UPDATE_INTERVAL_SECONDS = 5
TELEGRAM_MESSAGE_CHUNK_LIMIT = 4000
INITIAL_PROGRESS_SENTINEL = -10
STATUS_RECEIVED_TEXT = "⏳ Video လက်ခံရပါပြီ၊ Processing လုပ်နေပါတယ်..."
STATUS_DOWNLOADING_TEXT = "⏬ Video ကို download လုပ်နေပါတယ်..."
STATUS_EXTRACTING_TEXT = "🎵 Audio ထုတ်ယူနေပါတယ်..."
STATUS_TRANSCRIBING_TEXT = "🧠 Myanmar speech transcript လုပ်နေပါတယ်..."
STATUS_TTS_TEXT = "🔊 Voice reply ပြင်ဆင်နေပါတယ်..."
STATUS_UNSUPPORTED_DOCUMENT_TEXT = "❌ ဒီ document က video file မဟုတ်လို့ process မလုပ်နိုင်ပါ။"
STATUS_TTS_GENERATION_FAILED_TEXT = "⚠️ Transcript ပို့ပြီးပါပြီ။ Voice reply audio မဖန်တီးနိုင်သေးပါ။"
STATUS_VOICE_UPLOAD_FAILED_TEXT = "⚠️ Transcript ပို့ပြီးပါပြီ။ Voice message မပို့နိုင်သေးပါ။"
STATUS_PROCESSING_FAILED_TEXT = "❌ Processing မအောင်မြင်ပါ။ Video file ကို ပြန်စမ်းပို့ပေးပါ။"
_whisper_model_cache = None


def validate_config() -> int:
    missing = []
    for name, value in {
        "API_ID": API_ID,
        "API_HASH": API_HASH,
        "BOT_TOKEN": BOT_TOKEN,
    }.items():
        value_text = str(value).strip()
        lowered = value_text.lower()
        if not value_text or lowered.startswith("your_") or lowered.endswith("_here"):
            missing.append(name)

    if missing:
        raise RuntimeError(
            "Missing configuration: "
            + ", ".join(missing)
            + ". Please update your .env file before running the bot."
        )

    try:
        return int(API_ID)
    except ValueError as error:
        raise RuntimeError("API_ID must be a number.") from error


def get_whisper_model():
    global _whisper_model_cache
    if _whisper_model_cache is None:
        LOGGER.info("Loading Whisper model: %s", WHISPER_MODEL)
        _whisper_model_cache = whisper.load_model(WHISPER_MODEL)
    return _whisper_model_cache


def is_supported_document(message: Message) -> bool:
    document = message.document
    if not document:
        return False

    if document.mime_type and document.mime_type.startswith("video/"):
        return True

    file_name = document.file_name or ""
    return Path(file_name).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def media_suffix(message: Message) -> str:
    if message.document and message.document.file_name:
        suffix = Path(message.document.file_name).suffix
        if suffix:
            return suffix
    if message.video and message.video.file_name:
        suffix = Path(message.video.file_name).suffix
        if suffix:
            return suffix
    return ".mp4"


def split_transcript(text: str, limit: int = TELEGRAM_MESSAGE_CHUNK_LIMIT) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    chunks = []
    remaining = cleaned

    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def extract_audio(video_path: str, audio_path: str) -> None:
    try:
        (
            ffmpeg.input(video_path)
            .output(audio_path, ac=1, ar=16000, format="wav")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as error:
        stderr = error.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr or "ffmpeg failed while extracting audio.") from error


def transcribe_audio(audio_path: str) -> str:
    model = get_whisper_model()
    result = model.transcribe(
        audio_path,
        language="my",
        task="transcribe",
        fp16=torch.cuda.is_available(),
    )
    return (result.get("text") or "").strip()


async def create_voice_reply(text: str, output_path: str) -> None:
    mp3_path = str(Path(output_path).with_suffix(".mp3"))
    await edge_tts.Communicate(text=text, voice=TTS_VOICE).save(mp3_path)

    try:
        (
            ffmpeg.input(mp3_path)
            .output(output_path, format="ogg", acodec="libopus", ac=1, ar=48000)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as error:
        stderr = error.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr or "ffmpeg failed while converting TTS audio.") from error


async def safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except MessageNotModified:
        return
    except RPCError as error:
        LOGGER.warning("Unable to edit progress message: %s", error)


def build_progress_callback(status_message: Message) -> Callable[[int, int], None]:
    loop = asyncio.get_running_loop()
    progress_state = {"percent": INITIAL_PROGRESS_SENTINEL, "updated_at": 0.0}

    def progress(current: int, total: int) -> None:
        if total <= 0:
            return

        percent = int(current * 100 / total)
        now = loop.time()
        if (
            percent == 100
            or percent - progress_state["percent"] >= PROGRESS_UPDATE_THRESHOLD_PERCENT
            or now - progress_state["updated_at"] >= PROGRESS_UPDATE_INTERVAL_SECONDS
        ):
            progress_state["percent"] = percent
            progress_state["updated_at"] = now
            loop.create_task(
                safe_edit(
                    status_message,
                    f"{STATUS_DOWNLOADING_TEXT} {percent}%",
                )
            )

    return progress


async def send_transcript(message: Message, status_message: Message, transcript: str) -> None:
    chunks = split_transcript(transcript)
    if not chunks:
        raise ValueError("Whisper transcription produced an empty result.")

    await status_message.edit_text(f"📝 Transcript:\n\n{chunks[0]}")
    for chunk in chunks[1:]:
        await message.reply_text(chunk)


async def start_command(_: Client, message: Message) -> None:
    await message.reply_text(
        "မင်္ဂလာပါ 👋\n\n"
        "ဒီ bot က video ထဲက Myanmar voice ကို transcript ပြန်ထုတ်ပေးနိုင်ပါတယ်။\n"
        "Video file ပို့လိုက်ရုံနဲ့ processing လုပ်ပေးပါမယ်။"
    )


async def help_command(_: Client, message: Message) -> None:
    await message.reply_text(
        "အသုံးပြုနည်း\n\n"
        "1. Video / Video Note / Video document ပို့ပါ\n"
        "2. Bot က audio ထုတ်ယူပြီး Whisper နဲ့ transcript ပြောင်းပေးမယ်\n"
        "3. TTS ဖွင့်ထားရင် voice reply ပါပြန်ပို့မယ်\n\n"
        "Command များ:\n"
        "/start - welcome message\n"
        "/help - ဒီ usage guide\n"
        f"/model - လက်ရှိအသုံးပြုနေတဲ့ Whisper model ({WHISPER_MODEL})"
    )


async def model_command(_: Client, message: Message) -> None:
    await message.reply_text(f"🎙️ Current Whisper model: {WHISPER_MODEL}")


async def handle_video(client: Client, message: Message) -> None:
    if message.document and not is_supported_document(message):
        await message.reply_text(STATUS_UNSUPPORTED_DOCUMENT_TEXT)
        return

    status_message = await message.reply_text(STATUS_RECEIVED_TEXT)
    current_step = "download"

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / f"input{media_suffix(message)}"
            audio_path = temp_path / "audio.wav"
            voice_path = temp_path / "reply.ogg"

            await client.download_media(
                message,
                file_name=str(video_path),
                progress=build_progress_callback(status_message),
            )
            current_step = "audio extraction"
            await safe_edit(status_message, STATUS_EXTRACTING_TEXT)

            await asyncio.to_thread(extract_audio, str(video_path), str(audio_path))
            current_step = "transcription"
            await safe_edit(status_message, STATUS_TRANSCRIBING_TEXT)

            transcript = await asyncio.to_thread(transcribe_audio, str(audio_path))
            await send_transcript(message, status_message, transcript)

            if TTS_ENABLED:
                try:
                    current_step = "TTS generation"
                    await message.reply_text(STATUS_TTS_TEXT)
                    await create_voice_reply(transcript, str(voice_path))
                    current_step = "voice upload"
                    await message.reply_voice(str(voice_path), caption="🔊 Myanmar voice reply")
                except (OSError, RuntimeError, ValueError, RPCError):
                    LOGGER.exception("TTS reply failed during %s", current_step)
                    if current_step == "voice upload":
                        await message.reply_text(STATUS_VOICE_UPLOAD_FAILED_TEXT)
                    else:
                        await message.reply_text(STATUS_TTS_GENERATION_FAILED_TEXT)
    except (OSError, RuntimeError, ValueError, RPCError):
        LOGGER.exception("Video processing failed during %s", current_step)
        await safe_edit(status_message, STATUS_PROCESSING_FAILED_TEXT)


def main() -> None:
    api_id = validate_config()
    app = Client("video-transcriber", api_id=api_id, api_hash=API_HASH, bot_token=BOT_TOKEN)
    app.add_handler(MessageHandler(start_command, filters.command("start")))
    app.add_handler(MessageHandler(help_command, filters.command("help")))
    app.add_handler(MessageHandler(model_command, filters.command("model")))
    app.add_handler(MessageHandler(handle_video, filters.video | filters.video_note | filters.document))
    LOGGER.info("Bot is starting with Whisper model: %s", WHISPER_MODEL)
    app.run()


if __name__ == "__main__":
    main()
