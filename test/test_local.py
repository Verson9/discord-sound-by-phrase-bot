"""Test wake-phrase recognition locally (mic or audio file). No Discord needed.

Usage:
  make test-local
  make test-local FILE=clip.mp3
  python test/test_local.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from vosk import KaldiRecognizer, Model, SetLogLevel

from track_config import ROOT, combined_grammar, load_all_tracks, match_any_track

load_dotenv(ROOT / ".env")
SetLogLevel(-1)

TRACKS = load_all_tracks()
SAMPLE_RATE = TRACKS[0].sample_rate
GRAMMAR = combined_grammar(TRACKS)


def feed(rec: KaldiRecognizer, pcm: bytes) -> None:
    if rec.AcceptWaveform(pcm):
        text = json.loads(rec.Result()).get("text", "")
        kind = "heard"
    else:
        text = json.loads(rec.PartialResult()).get("partial", "")
        kind = "partial"
    if not text:
        return
    print(f"{kind}: {text}", flush=True)
    matched = match_any_track(TRACKS, text)
    if matched:
        track, hit = matched
        print(f"*** TRIGGER track={track.name!r} phrase={hit!r} ***", flush=True)
        rec.Reset()


def run_file(path: str) -> None:
    print(f"Decoding {path} → {SAMPLE_RATE} Hz mono via ffmpeg…")
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-i",
            path,
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    model = Model(str(TRACKS[0].model_path))
    rec = KaldiRecognizer(model, SAMPLE_RATE, GRAMMAR)
    pcm = proc.stdout
    step = SAMPLE_RATE * 2 // 10
    for i in range(0, len(pcm), step):
        feed(rec, pcm[i : i + step])
    final = json.loads(rec.FinalResult()).get("text", "")
    if final:
        print(f"final: {final}", flush=True)
        matched = match_any_track(TRACKS, final)
        if matched:
            track, hit = matched
            print(f"*** TRIGGER track={track.name!r} phrase={hit!r} ***", flush=True)


def run_mic() -> None:
    try:
        import sounddevice as sd
    except ImportError:
        print("Mic mode needs: pip install sounddevice")
        print("Or test a file: make test-local FILE=your.mp3")
        sys.exit(1)

    model = Model(str(TRACKS[0].model_path))
    rec = KaldiRecognizer(model, SAMPLE_RATE, GRAMMAR)
    print("Listening on mic — say a track phrase. Ctrl+C to stop.\n")

    def callback(indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        feed(rec, bytes(indata))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=SAMPLE_RATE // 10,
        dtype="int16",
        channels=1,
        callback=callback,
    ):
        while True:
            sd.sleep(1000)


def main() -> None:
    print(f"Active tracks: {[t.name for t in TRACKS]}")
    for t in TRACKS:
        print(f"  - {t.name}: {t.phrases}")
    print(f"Grammar: {GRAMMAR}")
    if len(sys.argv) > 1:
        run_file(sys.argv[1])
    else:
        run_mic()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
