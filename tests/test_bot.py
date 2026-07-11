import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


def install_stub_modules() -> None:
    class DummyFilter:
        def __or__(self, other):
            return self

    class DummyFilters:
        video = DummyFilter()
        video_note = DummyFilter()
        document = DummyFilter()

        def command(self, *_args, **_kwargs):
            return DummyFilter()

    class DummyClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def add_handler(self, *_args, **_kwargs):
            pass

        def run(self):
            pass

    pyrogram_module = types.ModuleType("pyrogram")
    pyrogram_module.Client = DummyClient
    pyrogram_module.filters = DummyFilters()

    pyrogram_errors = types.ModuleType("pyrogram.errors")

    class MessageNotModified(Exception):
        pass

    class RPCError(Exception):
        pass

    pyrogram_errors.MessageNotModified = MessageNotModified
    pyrogram_errors.RPCError = RPCError

    pyrogram_handlers = types.ModuleType("pyrogram.handlers")

    class MessageHandler:
        def __init__(self, callback, filters=None):
            self.callback = callback
            self.filters = filters

    pyrogram_handlers.MessageHandler = MessageHandler

    pyrogram_types = types.ModuleType("pyrogram.types")

    class Message:
        pass

    pyrogram_types.Message = Message

    edge_tts_module = types.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, *args, **kwargs):
            pass

        async def save(self, _path):
            pass

    edge_tts_module.Communicate = Communicate

    ffmpeg_module = types.ModuleType("ffmpeg")

    class FFmpegError(Exception):
        def __init__(self, stderr=b""):
            super().__init__("ffmpeg failed")
            self.stderr = stderr

    ffmpeg_module.Error = FFmpegError
    ffmpeg_module.input = Mock()

    torch_module = types.ModuleType("torch")
    torch_module.cuda = types.SimpleNamespace(is_available=lambda: False)

    whisper_module = types.ModuleType("whisper")
    whisper_module.load_model = Mock()

    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = Mock()

    sys.modules.update(
        {
            "pyrogram": pyrogram_module,
            "pyrogram.errors": pyrogram_errors,
            "pyrogram.handlers": pyrogram_handlers,
            "pyrogram.types": pyrogram_types,
            "edge_tts": edge_tts_module,
            "ffmpeg": ffmpeg_module,
            "torch": torch_module,
            "whisper": whisper_module,
            "dotenv": dotenv_module,
        }
    )


install_stub_modules()
bot = importlib.import_module("bot")


class BotHelpersTest(unittest.TestCase):
    def test_split_transcript_handles_empty_text(self):
        self.assertEqual(bot.split_transcript(""), [])

    def test_split_transcript_respects_limit(self):
        transcript = "a" * (bot.TELEGRAM_MESSAGE_CHUNK_LIMIT + 20)
        chunks = bot.split_transcript(transcript)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= bot.TELEGRAM_MESSAGE_CHUNK_LIMIT for chunk in chunks))
        self.assertEqual("".join(chunks), transcript)

    def test_split_transcript_prefers_newlines_and_spaces(self):
        transcript = ("ပထမစာကြောင်း\n" * 300) + ("မြန်မာ စာသား " * 300)
        chunks = bot.split_transcript(transcript)
        normalize = lambda value: "".join(value.split())

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= bot.TELEGRAM_MESSAGE_CHUNK_LIMIT for chunk in chunks))
        self.assertEqual(normalize("".join(chunks)), normalize(transcript))

    def test_extract_audio_includes_ffmpeg_stderr_in_error(self):
        pipeline = Mock()
        pipeline.output.return_value = pipeline
        pipeline.overwrite_output.return_value = pipeline
        pipeline.run.side_effect = bot.ffmpeg.Error(b"broken input")

        with patch.object(bot.ffmpeg, "input", return_value=pipeline):
            with self.assertRaises(RuntimeError) as context:
                bot.extract_audio("video.mp4", "audio.wav")

        self.assertIn("broken input", str(context.exception))

    def test_transcribe_audio_uses_myanmar_language(self):
        model = Mock()
        model.transcribe.return_value = {"text": " မင်္ဂလာပါ "}

        with patch.object(bot, "get_whisper_model", return_value=model), patch.object(
            bot.torch.cuda, "is_available", return_value=False
        ):
            result = bot.transcribe_audio("audio.wav")

        self.assertEqual(result, "မင်္ဂလာပါ")
        model.transcribe.assert_called_once_with(
            "audio.wav",
            language="my",
            task="transcribe",
            fp16=False,
        )

    def test_create_voice_reply_generates_mp3_and_ogg(self):
        pipeline = Mock()
        pipeline.output.return_value = pipeline
        pipeline.overwrite_output.return_value = pipeline
        communicate = Mock()
        communicate.save = AsyncMock()

        with patch.object(bot.edge_tts, "Communicate", return_value=communicate) as communicate_class, patch.object(
            bot.ffmpeg, "input", return_value=pipeline
        ) as ffmpeg_input:
            asyncio.run(bot.create_voice_reply("hello", "/tmp/reply.ogg"))

        communicate_class.assert_called_once_with(text="hello", voice=bot.TTS_VOICE)
        communicate.save.assert_awaited_once_with("/tmp/reply.mp3")
        ffmpeg_input.assert_called_once_with("/tmp/reply.mp3")
        pipeline.output.assert_called_once_with(
            "/tmp/reply.ogg",
            format="ogg",
            acodec="libopus",
            ac=1,
            ar=48000,
        )


if __name__ == "__main__":
    unittest.main()
