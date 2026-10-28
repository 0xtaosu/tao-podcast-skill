# Agent Instructions

## Goal

Use this repository to export a podcast transcript as:

- `<podcast-name> - <title>.txt` when podcast name is already available
- otherwise `<title>.txt`
- optionally an Obsidian note rendered from `Template/Podcast.md`

No `.meta.json` sidecar is produced.

The user will usually give you a link or a plain episode title.

## Required First Steps

Before the first real transcript run on a machine:

```bash
bash run.sh --doctor
```

Only continue to the real transcript command when `--doctor` exits with code `0`.

If `--doctor` fails:

1. Stop the transcript run.
2. Show the failing `DOCTOR` lines.
3. Tell the user to fix the missing dependency or permission issue first.

## Real Transcript Command

```bash
bash run.sh \
  --input "<episode-link-or-title>" \
  --out-dir "<output-dir>"
```

If the input is likely to require audio fallback, you may use:

```bash
bash run.sh \
  --input "<episode-link-or-title>" \
  --asr-model small \
  --out-dir "<output-dir>"
```

Use `small` by default unless the user explicitly wants the slower `medium` model.

## Output Contract

Treat the run as successful only when stdout contains:

- `OK    <txt-path>`
- `NOTE  <note-path>` when `--note-dir` / `--note-template` are used

After success:

1. Return the generated `.txt` path (and the `.md` note when requested).
2. Briefly state which resolver path was used.
3. Remind the user that the transcript is a draft and should get one proofreading pass before publishing.

For `Readwise/Podcast`, add the note flags to the same run:

```bash
bash run.sh \
  --input "<episode-url>" \
  --page-text-fallback off \
  --asr-model small \
  --out-dir "/tmp/transcripts" \
  --note-dir "Readwise/Podcast" \
  --note-template "Template/Podcast.md"
```

The renderer fills metadata, chapters, transcript and extraction status; it leaves `Summary` / `Bullet point` for the agent to write and proofread. No `meta.json` is written.

## Failure Contract

If stdout/stderr contains:

- `FAIL <input> <error>`

then do not pretend the run worked.

Return:

1. the exact failed input,
2. the exact error,
3. the next concrete fix.

## Notes

- This repo is designed for direct agent use after dependency install and `--doctor` success.
- For YouTube links, try the built-in chain: official transcript -> subtitles -> local audio ASR fallback.
- For plain titles, prefer Scripod official transcript matches before YouTube search.
- For direct audio URLs, go straight to ASR instead of transcript-page parsing.
- Do not assume YouTube subtitles or official transcripts always exist.
- Local ASR fallback depends on `faster-whisper`.
- Do not describe the repo as publish-ready transcript quality; it produces a working draft.


## Local storage and output mode

Install dependencies only in the external venv described in SKILL.md, never in a synced vault. Doctor success does not mean model weights are downloaded. For episode-page transcript or ASR requests, add `--page-text-fallback off`; otherwise the default may return only show notes. Inspect metadata before claiming transcript success. Do not create speaker drafts from show notes.
