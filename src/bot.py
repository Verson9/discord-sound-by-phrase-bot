"""Discord bot that listens in a voice channel and plays a sound
when someone says a trigger phrase. py-cord + Vosk (offline recognition)."""
import asyncio
import json
import logging
import os
import time

import discord
import numpy as np
from dotenv import load_dotenv
from vosk import KaldiRecognizer, Model, SetLogLevel

from track_config import (
    ROOT,
    TrackConfig,
    combined_grammar,
    load_all_tracks,
    match_any_track,
)

load_dotenv(ROOT / ".env")
SetLogLevel(-1)
logging.basicConfig(level=logging.INFO)
logging.getLogger("discord.voice").setLevel(logging.INFO)

# Homebrew libopus is not on the default ctypes search path on Apple Silicon.
if not discord.opus.is_loaded():
    for path in (
        "/opt/homebrew/lib/libopus.dylib",
        "/usr/local/lib/libopus.dylib",
        "libopus.dylib",
        "libopus.so.0",
    ):
        try:
            discord.opus.load_opus(path)
            if discord.opus.is_loaded():
                break
        except Exception:
            continue
if not discord.opus.is_loaded():
    raise RuntimeError("libopus not found — brew install opus")
print(f"opus: {discord.opus._OpusStruct.get_opus_version()}", flush=True)

TOKEN = os.environ["DISCORD_TOKEN"]
ONLY_USER_ID = int(os.getenv("ONLY_USER_ID", "0"))  # 0 = react to everyone

TRACKS = load_all_tracks()
SAMPLE_RATE = TRACKS[0].sample_rate
GRAMMAR = combined_grammar(TRACKS)
model = Model(str(TRACKS[0].model_path))
for t in TRACKS[1:]:
    if t.model_path != TRACKS[0].model_path:
        print(
            f"warning: track {t.name} uses model {t.model_path}, "
            f"but recognizer uses {TRACKS[0].model_path}",
            flush=True,
        )
    if t.sample_rate != SAMPLE_RATE:
        print(
            f"warning: track {t.name} sample_rate={t.sample_rate}, "
            f"using {SAMPLE_RATE}",
            flush=True,
        )

# Python 3.12+ has no default event loop; py-cord still calls get_event_loop().
asyncio.set_event_loop(asyncio.new_event_loop())
bot = discord.Bot(intents=discord.Intents.default())

print(f"loaded {len(TRACKS)} track(s): {[t.name for t in TRACKS]}", flush=True)
for t in TRACKS:
    print(f"  - {t.name}: {t.sound_file.name} phrases={t.phrases}", flush=True)


def to_16k_mono(pcm: bytes) -> bytes:
    """Discord gives 48 kHz stereo s16le; Vosk wants 16 kHz mono."""
    a = np.frombuffer(pcm, dtype=np.int16)
    # stereo 48k -> mono 16k: average L/R and take every 3rd frame
    n = len(a) - (len(a) % 6)
    if n < 6:
        return b""
    return a[:n].reshape(-1, 6).mean(axis=1).astype(np.int16).tobytes()


class TriggerSink(discord.sinks.Sink):
    """Receives per-user PCM in real time and checks it for any track phrase."""

    def __init__(self, on_trigger):
        super().__init__()
        self.on_trigger = on_trigger
        self.recognizers = {}
        self.packets = 0
        self.bytes_seen = 0

    def write(self, data, user):  # called from the voice receive thread
        uid = getattr(user, "id", user)
        if ONLY_USER_ID and uid != ONLY_USER_ID:
            return
        if hasattr(data, "pcm"):
            data = data.pcm
        if not data:
            return

        self.packets += 1
        self.bytes_seen += len(data)
        if self.packets == 1 or self.packets % 50 == 0:
            print(
                f"[audio] packets={self.packets} bytes={self.bytes_seen} user={uid}",
                flush=True,
            )

        rec = self.recognizers.get(uid)
        if rec is None:
            rec = self.recognizers[uid] = KaldiRecognizer(model, SAMPLE_RATE, GRAMMAR)
            print(f"[audio] grammar recognizer for user={uid}", flush=True)

        pcm = to_16k_mono(data)
        if not pcm:
            return
        if rec.AcceptWaveform(pcm):
            text = json.loads(rec.Result()).get("text", "")
            if text:
                print(f"[{uid}] heard: {text}", flush=True)
        else:
            text = json.loads(rec.PartialResult()).get("partial", "")
            if text and text != getattr(self, "_last_partial", None):
                self._last_partial = text
                print(f"[{uid}] partial: {text}", flush=True)
        matched = match_any_track(TRACKS, text) if text else None
        if matched:
            track, hit = matched
            print(f"[{uid}] trigger matched track={track.name!r} phrase={hit!r}", flush=True)
            rec.Reset()
            self.on_trigger(uid, track)


async def _done(sink, *args):
    print(
        f"[audio] recording stopped; packets={getattr(sink, 'packets', 0)}",
        flush=True,
    )


@bot.slash_command(name="join-cry", description="Join your voice channel and start listening")
async def join(ctx: discord.ApplicationContext):
    if not ctx.author.voice:
        return await ctx.respond("Join a voice channel first.", ephemeral=True)

    await ctx.defer()
    try:
        if ctx.voice_client and ctx.voice_client.is_connected():
            vc = ctx.voice_client
            if vc.is_recording():
                vc.stop_recording()
        else:
            if ctx.voice_client:
                await ctx.voice_client.disconnect(force=True)
            vc = await ctx.author.voice.channel.connect()

        if hasattr(vc, "wait_until_connected"):
            ok = vc.wait_until_connected(timeout=10)
            if not ok:
                return await ctx.followup.send(
                    "Nie udało się połączyć z kanałem głosowym. Spróbuj ponownie."
                )
        else:
            for _ in range(50):
                if vc.is_connected():
                    break
                await asyncio.sleep(0.1)
            else:
                return await ctx.followup.send(
                    "Nie udało się połączyć z kanałem głosowym. Spróbuj ponownie."
                )

        dave = getattr(vc, "is_dave_connection", lambda: False)()
        print(
            f"[voice] connected={vc.is_connected()} dave={dave} channel={ctx.author.voice.channel}",
            flush=True,
        )

        loop = asyncio.get_running_loop()
        last_by_track: dict[str, float] = {}

        def play(track: TrackConfig):
            if vc.is_connected() and not vc.is_playing():
                vc.play(discord.FFmpegPCMAudio(str(track.sound_file)))

        def on_trigger(user_id, track: TrackConfig):
            now = time.monotonic()
            if now - last_by_track.get(track.name, 0.0) < track.cooldown_seconds:
                return
            last_by_track[track.name] = now
            print(f"Trigger heard from {user_id} → {track.name}", flush=True)
            loop.call_soon_threadsafe(play, track)

        sink = TriggerSink(on_trigger)
        vc.start_recording(sink, _done)
        print(f"[voice] recording={vc.is_recording()}", flush=True)
        await ctx.followup.send("Joined.", ephemeral=True)
    except Exception as e:
        print(f"join-cry failed: {e!r}", flush=True)
        await ctx.followup.send(f"Błąd: {e}", ephemeral=True)


@bot.slash_command(name="leave-cry", description="Stop listening and leave")
async def leave(ctx: discord.ApplicationContext):
    vc = ctx.voice_client
    if not vc:
        return await ctx.respond("I'm not in a voice channel.", ephemeral=True)
    try:
        if vc.is_recording():
            vc.stop_recording()
    except Exception as e:
        print(f"stop_recording: {e!r}", flush=True)
    await vc.disconnect()
    await ctx.respond("Left the channel.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}", flush=True)
    print(f"Active tracks: {[t.name for t in TRACKS]}", flush=True)
    guild_ids = [g.id for g in bot.guilds]
    if guild_ids:
        await bot.sync_commands(guild_ids=guild_ids)
        print(f"Synced slash commands to guilds: {guild_ids}", flush=True)
    else:
        await bot.sync_commands()
        print("Synced global slash commands (may take a few minutes)", flush=True)


bot.run(TOKEN)
