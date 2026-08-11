# video-editor (Claude Code skill for DaVinci Resolve)

A Claude Code skill that turns a raw voiceover recording into a fast-cut, meme/b-roll-driven,
captioned edit inside DaVinci Resolve — automatically. You give it a narration recording (plus
an optional script), and it transcribes, trims silence and filler words without ever cutting a
word in half, writes punchy synced captions, picks emotionally/contextually matching clips for
each sentence from your own media library (or free stock), and assembles all of it into a
DaVinci Resolve project it renders a draft from.

Full workflow, pipeline stages, and file schemas live in [`SKILL.md`](./SKILL.md) — that's the
file Claude actually reads when this skill triggers. Everything below is just human-facing setup.

## Требования (коротко, по-русски)

Это работает **только локально**, на компьютере с установленным и запущенным DaVinci Resolve —
скриптовый API Resolve не достаёт до облака. Установите на свой компьютер: DaVinci Resolve
(Free или Studio), Python 3.9+, `ffmpeg`/`ffprobe`, и `pip3 install -r requirements.txt`. Затем
включите в Resolve: Preferences → General → **External scripting using → Local** (перезапустить
Resolve). Дальше просто зовите Claude Code в папке с этим скиллом и с вашим проектом — он сам
проведёт вас по шагам (`SKILL.md` и `scripts/check_environment.py` первым делом проверят, что
всё на месте).

## Install as a Claude Code skill

Clone this repo somewhere Claude Code looks for skills, e.g. as a personal skill:

```bash
git clone <this-repo-url> ~/.claude/skills/video-editor
```

or as a project-scoped skill inside a specific project's `.claude/skills/` folder. Claude Code
will pick up `SKILL.md`'s frontmatter and offer to use it whenever you ask it to edit/assemble a
video, add auto-captions, or build a DaVinci Resolve project from a voiceover.

## One-time local setup

```bash
pip3 install -r requirements.txt
python3 scripts/check_environment.py
```

Fix whatever it flags (it prints exact commands / env vars per OS — see
`references/resolve_scripting_api.md` for the full detail) before running the pipeline.

## Layout

```
SKILL.md                    the skill itself — read this first
scripts/                     the deterministic pipeline stages (transcribe, cut planning,
                                 captions, media indexing, stock fetch) + DaVinci Resolve
                                 automation in scripts/resolve/
references/                 schemas + the Resolve scripting API cheat sheet
assets/style-profiles/       the default "fast-explainer" style profile — copy per channel
config.example.json          copy to config.json and fill in your media library path / keys
```

## Media library and stock

Keep your own collected clips/memes/reaction footage in one long-lived folder outside this repo
(point `config.json`'s `media_library_path` at it). This skill tags it for you — see step 4 in
`SKILL.md` — instead of asking you to organize it by hand. Free stock (Pexels/Pixabay/Giphy) can
fill gaps; each needs its own free API key set as an environment variable, see
`references/media_tagging_schema.md` for licensing notes per provider (Giphy in particular has
commercial-use restrictions worth knowing about).
