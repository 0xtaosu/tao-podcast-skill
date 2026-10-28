---
name: tao-podcast-transcript
description: Deterministic workflow to find and export full podcast transcripts as cleaned TXT files from YouTube URLs, episode webpages (including Xiaoyuzhou), Apple Podcasts title search, X/Twitter links, direct audio URLs, or plain episode titles, and optionally render an Obsidian note from Template/Podcast.md. Use when users ask for 逐字稿/文字版/transcript/txt or ask to add a podcast episode to Readwise/Podcast.
---

# TAO Podcast Transcript

## Overview
Produce clean TXT transcript-like outputs for podcast/video episodes with a fixed decision tree.
Prioritize official transcript sources first, then platform subtitles or official page text, then local ASR fallback.
ASR fallback uses `faster-whisper` with selectable `--asr-model small|medium` (default `small`).
For podcast episodes, the same run can render an Obsidian note from `Template/Podcast.md`.
No `.meta.json` sidecar is written; extraction details stay in memory and in the note's 提取状态.
All transcript outputs are working drafts; always recommend one strong-LLM proofreading pass.

## Match the requested output

- Adding an episode or saving listening notes: page descriptions are acceptable, but label them as show notes, not transcripts. Check for an existing note with the same source URL before creating a duplicate.
- Transcript or ASR requests for episode webpages: use `--page-text-fallback off` so descriptions cannot prematurely satisfy the request. The executor still tries supported official transcript parsing before audio ASR.
- Inspect the resolver and attempt log printed by the run. Exit code 0 means extraction succeeded, not necessarily that a full transcript exists.
- Failure to extract subtitles does not prove the platform has none.

## Workflow Decision Tree

1. Normalize input.
- Accept one or more `--input` values.
- Support (stable): YouTube URL/ID, episode webpages (including Xiaoyuzhou), direct audio URLs, or plain title.
- X/Twitter status URL: best-effort resolver to outbound sources.

2. Resolve canonical episode source.
- Stable path A: if input is YouTube URL/ID, use it directly.
- Stable path B: if input is direct official transcript URL/JSON, parse it directly.
- Stable path B2: if input is a local official transcript file (`.ttml`, supported `.json`), parse it directly.
- Stable path C: if input is direct audio URL, go to local ASR path.
- Stable path D: if input is episode webpage, attempt transcript parse, then structured page text, then extract `og:audio`/JSON-LD audio as ASR source.
- Stable path E: if input is plain title, resolve with `ytsearch1`, then Scripod `search -> channel -> transcript` resolver, then Apple `podcastEpisode` search fallback.
- Optional path: if input is X/Twitter URL, try outbound link resolution or compact title hint fallback, then follow A-E.

3. Fetch transcript in strict priority order.
- Priority A: official transcript/API source from episode host (including YouTube description outbound links).
- Priority B: platform subtitles via `yt-dlp` (`youtube:player_client=android`).
- Priority C: structured page text from episode webpage when it is clearly visible and substantial.
- Priority D: local ASR fallback when A/B/C unavailable and an audio source is available (`faster-whisper`, `--asr-model small|medium`, default `small`).

4. Error and boundary handling.
- If A/B/C all fail, return exact failed stage and error detail.
- Record every step in the in-memory attempt log (printed for debugging, never written as a sidecar file).
- Do not bypass login/paywall/DRM protections.

5. Clean and export.
- Remove timestamp markup and HTML tags.
- Collapse rolling-caption duplication.
- Run readability quality checks; if needed, apply aggressive secondary splitting.
- Keep paragraph-level readability.
- Write one TXT file per input item.

6. Post-process actual transcripts after step 5.
- Do not assign speakers to show notes or page descriptions.
- Create a speaker draft for actual transcripts; attribution is inferred, not diarization.
- Input: the transcript from step 5 + the run metadata (title, description, shownotes, chapters).
- Optionally generate `<same-base-name>.body-cleaned.txt`: remove only pure ads / pure housekeeping / pure subscribe reminders, keep all substantive conversation verbatim, and prefer this file for `*.speaker-draft.txt` when present.
- Extract speaker hints from metadata: episode title, guest name mentions, intro/outro text.
- Re-read the transcript and annotate each paragraph with the most likely speaker.
- Format each turn as `[Name]: text`. If uncertain, use `[?]: text`.
- For ASR-derived transcripts: names and terms may have phonetic errors — cross-reference metadata to correct obvious mismatches before attributing.
- Do not invent speaker names not inferable from the transcript or metadata.
- Output: `<same-base-name>.speaker-draft.txt` alongside the existing `*.txt`. Never overwrite the original transcript.
- Add a header identifying inferred attribution and the actual source type; use `ASR source` only for ASR output.

7. Generate the Obsidian note when the target is `Readwise/Podcast`.
- Add `--note-dir "<vault>/Readwise/Podcast"` and `--note-template "<vault>/Template/Podcast.md"` to the main command; the note is rendered in the same run, with no intermediate `meta.json`.
- The renderer fills YAML, About fields, 收听索引, Transcript, and 提取状态, and strips the template's `%%` block.
- `Summary` and `Bullet point` are intentionally left blank: write them after generation from the transcript, then proofread names and terms.
- It refuses to overwrite an existing note with the same `url` or the same filename unless `--note-force`; prefer editing the existing note instead.

## Deterministic Rules

1. Do not jump between random methods.
- Always follow A -> B -> C -> D.
- D requires an audio source (direct audio URL / episode webpage audio / Apple episode audio).
- Record the failure reason before moving to next tier.

2. Default security posture.
- Do not use browser cookies unless explicitly required and approved.
- Do not upload private audio/video to third-party transcript sites.

3. Failure reporting contract.
- Return: failed stage, exact error type, and next action already attempted.
- Keep each attempt in the in-memory log so failures can be reported precisely.
- If blocked after A/B/C, return one minimal user command to unblock.

4. Delivery quality contract.
- Explicitly state that output TXT may be transcript, subtitle-derived text, or visible page text depending on resolver.
- Explicitly recommend one strong-LLM proofreading pass for names/terms/punctuation.
- Keep this notice concise but always present in final user-facing delivery.
- Default to `small` for ASR; preserve an existing user choice. Explain that `medium` needs more storage and processing time when relevant, without requiring repeated confirmation.
- Remind users that delivery is the `*.txt` (and the `.md` note when `--note-dir` is used); no `*.meta.json` is produced.

## Quick Start

Run (recommended stable usage):

```bash
bash run.sh \
  --input "https://www.youtube.com/watch?v=n1E9IZfvGMA" \
  --input "播客标题关键词" \
  --out-dir "/tmp/transcripts"
```

Outputs:
- `<podcast-name> - <title>.txt` when podcast name is already available
- otherwise `<title>.txt`

For a podcast note in the vault, add the note flags to the same command:

```bash
bash run.sh \
  --input "<episode-url>" \
  --page-text-fallback off \
  --asr-model small \
  --out-dir "/tmp/transcripts" \
  --note-dir "Readwise/Podcast" \
  --note-template "Template/Podcast.md"
```

Outputs `OK <txt-path>` and `NOTE <note-path>`. The note is a scaffold, not a finished summary: fill `Summary` / `Bullet point` and proofread the transcript before calling it done.

## Host-Specific Notes

- `scripod.com`: prefer `/api/transcript/<episode_id>`; for plain titles use `/api/search/?entity=episode` then `/api/channel/?feedUrl=...` to resolve episode id.
- YouTube: use `yt-dlp` with `youtube:player_client=android`; try language set in this order: `zh-*` then `en-orig` then `en`.
- Xiaoyuzhou episode pages: prefer structured page text (`shownotes` / visible text), keep `transcriptMediaId` as a metadata clue, and only then fall back to audio ASR. The note renderer reads `__NEXT_DATA__` for title, podcast, people, publish date, duration, and chapters.
- Apple transcript files: parse `.ttml` directly instead of re-running ASR.

## References

- Source strategy and reliability matrix: `references/sources.md`

## Scripts

- Main executor: `scripts/podcast_transcript_txt.py`
- Obsidian note renderer (called by the executor): `scripts/obsidian_note.py`

## Local install notes

`run.sh` is a wrapper that keeps Python dependencies and ASR weights out of the skill directory — which matters when the skill lives inside a synced folder (iCloud, Dropbox) or inside another git repository.

```bash
bash run.sh --doctor
bash run.sh --input "<url-or-title>" --out-dir "<dir>"
```

It resolves the interpreter from `$PODCAST_SKILL_VENV` (default `~/.local/share/podcast-transcript-txt/venv`) and falls back to system `python3` with a warning when that venv is absent. It also pins `PODCAST_ASR_MODEL_ROOT` (default `~/.local/share/podcast-transcript-txt/models`).

One-time setup:

```bash
python3 -m venv ~/.local/share/podcast-transcript-txt/venv
~/.local/share/podcast-transcript-txt/venv/bin/pip install -U pip
~/.local/share/podcast-transcript-txt/venv/bin/pip install -r requirements.txt
```

Require `--doctor` to exit `0` before any real transcript run.


## Storage and maintenance

- Keep venvs, model weights, package caches and downloaded audio outside synced vaults; lightweight scripts and instructions may remain in the project.
- Default runtime root: `~/.local/share/podcast-transcript-txt/`; dependencies live in `venv/`, weights in `models/`. `PODCAST_SKILL_HOME` overrides the base, and `PODCAST_SKILL_VENV` / `PODCAST_ASR_MODEL_ROOT` override individual paths.
- Prefer `bash run.sh`; direct Python execution uses the same default model root but requires the correct interpreter.
- `--doctor` verifies dependencies and model-directory writability. It does not download weights or validate inference. First ASR use or `--bootstrap-models small` downloads weights.
- Audio processing uses system temporary directories. Stage the `.txt` in `/tmp`; the `.md` note goes straight to the requested vault folder. No `.meta.json` is written.
- Sandboxed agent runs may be unable to write `~/.local/share`; in that case set `PODCAST_ASR_MODEL_ROOT=/tmp/podcast-models` for the run, or run `--doctor` / ASR in a normal terminal.
- In this vault, edit `.agents/src/podcast-transcript-txt-skill/`, not generated `.agents/skills/tao-podcast-transcript/`. Deployment uses `.agents/scripts/sync-podcast-skill.sh` and requires a clean source checkout. Respect any user restriction against changing the generated directory.

Episode-page ASR command (when the requested transcription is permitted):

```bash
bash run.sh --input "<episode-url>" --page-text-fallback off --asr-model small --out-dir /tmp/transcripts
```
