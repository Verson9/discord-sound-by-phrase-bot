# Discord phrase-triggered sound bot

## Setup
1. Install ffmpeg (`brew install ffmpeg` / `sudo apt install ffmpeg`).
2. Use **Python 3.10–3.14** (3.15 is not supported by py-cord). Then:
   `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. Download a Vosk model from https://alphacephei.com/vosk/models
   (e.g. `vosk-model-small-en-us-0.15`, or `vosk-model-small-pl-0.22` for Polish),
   unzip it and rename the folder to `model` (path is set per-track in `config.yaml`).
4. Put each sound in its own folder under `music/`:
   `music/<track>/config.yaml` + audio file (see `music/baby_dont_cry/`).
   **All tracks are active** — matching a track's phrase plays that track's sound.
5. Discord Developer Portal -> New Application -> Bot -> copy token.
   Invite with scopes `bot` + `applications.commands` and permissions
   View Channels, Connect, Speak.
6. `cp .env.example .env`, fill in the token.
7. `make run` (runs `src/bot.py`), then use `/join-cry` while in a voice channel.

## Tips
- Use a 2-3 word trigger phrase that is in the model's vocabulary.
- Set ONLY_USER_ID to your own ID so it only reacts to you.
- Tell people in the channel that the bot is listening.
