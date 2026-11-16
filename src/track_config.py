"""Load per-track music config (phrases + Vosk model settings).

Layout (one folder per sound):
  music/<track_name>/
    config.yaml
    <audio file>
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"


@dataclass
class TrackConfig:
    name: str
    sound_file: Path
    phrases: list[str]
    model_path: Path
    sample_rate: int = 16000
    grammar_extra: list[str] = field(default_factory=list)
    normalize_map: dict[str, str] = field(default_factory=dict)
    fuzzy_groups: list[list[list[str]]] = field(default_factory=list)
    cooldown_seconds: float = 5.0

    def light_norm(self, text: str) -> str:
        return " ".join(text.lower().replace("'", "").replace("’", "").split())

    def match_norm(self, text: str) -> str:
        t = self.light_norm(text)
        for src, dst in self.normalize_map.items():
            t = t.replace(src, dst)
        return " ".join(t.split())

    @property
    def trigger_light(self) -> list[str]:
        return list(dict.fromkeys(self.light_norm(p) for p in self.phrases))

    @property
    def trigger_norms(self) -> list[str]:
        return list(dict.fromkeys(self.match_norm(p) for p in self.phrases))

    @property
    def grammar(self) -> str:
        entries = [*self.trigger_light, *self.grammar_extra, "[unk]"]
        return json.dumps(list(dict.fromkeys(entries)))

    def matches(self, text: str) -> str | None:
        light = self.light_norm(text)
        norm = self.match_norm(text)
        for raw in self.phrases:
            needle_light = self.light_norm(raw)
            needle_norm = self.match_norm(raw)
            if needle_norm and needle_norm in norm:
                return raw
            if needle_light and needle_light in light:
                return raw
        words = set(norm.split())
        for groups in self.fuzzy_groups:
            if all(
                any(opt in words or opt in norm for opt in group) for group in groups
            ):
                return f"fuzzy:{'-'.join(g[0] for g in groups)}"
        return None


def list_tracks() -> list[str]:
    """Names of tracks that have music/<name>/config.yaml."""
    if not MUSIC_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in MUSIC_DIR.iterdir()
        if p.is_dir() and (p / "config.yaml").is_file()
    )


def load_all_tracks() -> list[TrackConfig]:
    """Load every track under music/."""
    names = list_tracks()
    if not names:
        raise FileNotFoundError(f"No tracks found in {MUSIC_DIR}")
    return [load_track(name) for name in names]


def combined_grammar(tracks: list[TrackConfig]) -> str:
    """Merge grammar entries from all tracks for one Vosk recognizer."""
    entries: list[str] = []
    for t in tracks:
        entries.extend(t.trigger_light)
        entries.extend(t.grammar_extra)
    entries.append("[unk]")
    return json.dumps(list(dict.fromkeys(entries)))


def match_any_track(tracks: list[TrackConfig], text: str) -> tuple[TrackConfig, str] | None:
    """Return (track, phrase) for the best matching track, if any."""
    best: tuple[TrackConfig, str] | None = None
    best_len = -1
    for track in tracks:
        hit = track.matches(text)
        if hit and len(hit) > best_len:
            best = (track, hit)
            best_len = len(hit)
    return best


def load_track(name: str) -> TrackConfig:
    """Load music/<name>/config.yaml and its audio file."""
    track_dir = MUSIC_DIR / name
    cfg_path = track_dir / "config.yaml"
    if not cfg_path.is_file():
        available = ", ".join(list_tracks()) or "(none)"
        raise FileNotFoundError(
            f"Track config not found: {cfg_path}\nAvailable tracks: {available}"
        )

    with cfg_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    model = raw.get("model") or {}
    audio_name = raw.get("file") or f"{name}.mp3"
    sound = track_dir / audio_name
    if not sound.is_file():
        raise FileNotFoundError(f"Track audio not found: {sound}")

    model_path = Path(model.get("path", "model"))
    if not model_path.is_absolute():
        model_path = ROOT / model_path

    return TrackConfig(
        name=name,
        sound_file=sound,
        phrases=list(raw.get("phrases") or []),
        model_path=model_path,
        sample_rate=int(model.get("sample_rate", 16000)),
        grammar_extra=list(model.get("grammar_extra") or []),
        normalize_map={
            str(k): str(v) for k, v in (model.get("normalize") or {}).items()
        },
        fuzzy_groups=list(model.get("fuzzy") or []),
        cooldown_seconds=float(raw.get("cooldown_seconds", 5)),
    )
