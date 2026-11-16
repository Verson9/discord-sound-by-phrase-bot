.PHONY: run new-track test-local

run:
	PYTHONUNBUFFERED=1 .venv/bin/python src/bot.py

test-local:
	PYTHONUNBUFFERED=1 .venv/bin/python test/test_local.py $(FILE)

# Usage: make new-track NAME=my_sound
new-track:
	@bash scripts/new_track.sh "$(NAME)"
