#!/usr/bin/env python3
"""Render a podcast transcript + meta pair into an Obsidian note.

The note skeleton comes from a Markdown template (normally
``Template/Podcast.md``). Only deterministic fields are filled: frontmatter,
About fields, chapter index, transcript, and extraction status. Summary and
bullet points are left for the agent/reader.

Usage:
    python3 scripts/obsidian_note.py \
        --txt "/tmp/episode.txt" \
        --meta "/tmp/episode.meta.json" \
        --template "/vault/Template/Podcast.md" \
        --out-dir "/vault/Readwise/Podcast"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from podcast_transcript_txt import (  # noqa: E402
    compact_ws,
    extract_next_data,
    extract_og_content,
    http_get,
    nested_get_dict,
    sanitize_filename,
    seconds_to_hms,
    title_from_page_html,
)

CHAPTER_RE = re.compile(r"^\s*(?:[-*•·]\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")
TRANSCRIPT_LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+)$")


def parse_timestamp(value: str) -> Optional[int]:
    parts = value.strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def format_timestamp(sec: int) -> str:
    if sec < 3600:
        return f"{sec // 60:02d}:{sec % 60:02d}"
    return seconds_to_hms(sec)


def parse_chapters(text: str) -> List[Tuple[int, str]]:
    """Parse ``* 01:26 title`` lines, keeping timestamps monotonic.

    Show notes often nest a sub-item with an earlier timestamp under a chapter
    (e.g. ``15:19`` under ``15:42``); those are skipped so the transcript can
    be split by chapter boundaries.
    """
    chapters: List[Tuple[int, str]] = []
    last = -1
    for line in (text or "").splitlines():
        match = CHAPTER_RE.match(line)
        if not match:
            continue
        sec = parse_timestamp(match.group(1))
        if sec is None or sec <= last:
            continue
        title = compact_ws(re.sub(r"[*_`#]+", "", match.group(2))).strip(" -—·")
        if not title:
            continue
        chapters.append((sec, title))
        last = sec
    return chapters


def parse_transcript(text: str) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    for line in (text or "").splitlines():
        match = TRANSCRIPT_LINE_RE.match(line.strip())
        if not match:
            continue
        text_part = compact_ws(match.group(2))
        if not text_part:
            continue
        rows.append((parse_timestamp(match.group(1)) or 0, text_part))
    return rows


def merge_transcript(
    rows: List[Tuple[int, str]], max_chars: int = 220, gap_break: float = 2.5
) -> List[Tuple[int, str]]:
    """Merge tiny ASR segments into readable, timestamped paragraphs."""
    paras: List[Tuple[int, str]] = []
    buf: List[str] = []
    start: Optional[int] = None
    for index, (sec, text) in enumerate(rows):
        if start is None:
            start = sec
        buf.append(text)
        merged = "".join(buf)
        next_sec = rows[index + 1][0] if index + 1 < len(rows) else None
        gap = next_sec - sec if next_sec is not None else None
        if (
            len(merged) >= max_chars
            or (len(merged) >= 120 and re.search(r"[。！？]$", merged))
            or (gap is not None and gap >= gap_break)
        ):
            paras.append((start, merged))
            buf = []
            start = None
    if buf and start is not None:
        paras.append((start, "".join(buf)))
    return paras


def _set_frontmatter(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    replacement = f"{key}: {value}".rstrip()
    if pattern.search(text):
        return pattern.sub(lambda _m: replacement, text, count=1)
    return text


def _set_inline(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}::.*$", re.M)
    replacement = f"{key}:: {value}".rstrip()
    if pattern.search(text):
        return pattern.sub(lambda _m: replacement, text, count=1)
    return text


def _replace_section(text: str, title: str, body: str) -> str:
    marker = f"## {title}"
    start = text.find(marker)
    if start < 0:
        return text
    after = text.find("\n", start)
    if after < 0:
        return text
    after += 1
    next_heading = re.search(r"^## ", text[after:], re.M)
    end = after + next_heading.start() if next_heading else len(text)
    return text[:after] + "\n" + body.strip("\n") + "\n\n" + text[end:]


def _yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def guess_people(description: str) -> Tuple[str, str]:
    host = guest = ""
    host_match = re.search(r"(?:主播|主持|导游)[：:]\s*([^\n，,。；;（(]{1,30})", description or "")
    if host_match:
        host = compact_ws(host_match.group(1))
    guest_match = re.search(
        r"(?:嘉宾|对谈|珍藏|做客)[：:]\s*([^\n，,。；;（(]{1,30})", description or ""
    )
    if guest_match:
        guest = compact_ws(guest_match.group(1))
    if host and guest and host == guest:
        guest = ""
    return host, guest


def collect_page_info(url: str, page_html: Optional[str] = None) -> Dict[str, Any]:
    info: Dict[str, Any] = {"url": url, "title": "", "podcast": "", "description": "", "published": "", "duration_sec": 0}
    try:
        page = page_html if page_html is not None else http_get(url, timeout=30)
    except Exception:
        return info

    host = urlparse(url).netloc.lower()
    if "xiaoyuzhoufm.com" in host:
        data = extract_next_data(page)
        episode = nested_get_dict(data, "props", "pageProps", "episode")
        podcast = nested_get_dict(episode, "podcast")
        info.update(
            {
                "title": compact_ws(str(episode.get("title") or "")),
                "podcast": compact_ws(str(podcast.get("title") or "")),
                "description": str(episode.get("description") or ""),
                "published": str(episode.get("pubDate") or "")[:10],
                "duration_sec": int(episode.get("duration") or 0),
            }
        )
        return info

    info["title"] = title_from_page_html(page)
    info["description"] = extract_og_content(page, "og:description") or ""
    info["published"] = (extract_og_content(page, "article:published_time") or "")[:10]
    return info


def _existing_note(out_dir: Path, url: str) -> Optional[Path]:
    for path in out_dir.glob("*.md"):
        try:
            if f'url: "{url}"' in path.read_text(encoding="utf-8") or f"url: {url}" in path.read_text(encoding="utf-8"):
                return path
        except OSError:
            continue
    return None


def render_note_from_files(
    txt_path: Path, meta_path: Path, template_path: Path, out_dir: Path, force: bool = False
) -> Path:
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    template = Path(template_path).read_text(encoding="utf-8")
    rows = parse_transcript(Path(txt_path).read_text(encoding="utf-8"))
    if not rows:
        raise RuntimeError(f"no timestamped transcript lines in {txt_path}")

    url = str(meta.get("input") or meta.get("source") or "")
    info = collect_page_info(url)
    title = info.get("title") or Path(txt_path).stem
    podcast = info.get("podcast") or compact_ws(str(meta.get("podcast_name") or ""))
    description = info.get("description") or ""
    host, guest = guess_people(description)
    published = info.get("published") or ""
    duration_sec = int(info.get("duration_sec") or meta.get("asr", {}).get("duration_sec") or 0)
    duration = f"~{max(1, round(duration_sec / 60))} min" if duration_sec else ""
    resolver = str(meta.get("resolver") or "")
    if "asr" in resolver:
        transcript_status = "asr-draft"
    elif "subtitle" in resolver or "official" in resolver:
        transcript_status = "official"
    elif "page-text" in resolver:
        transcript_status = "show-notes-only"
    else:
        transcript_status = ""

    chapters = parse_chapters(description)
    if not chapters:
        chapters = [(0, "开场")]
    elif chapters[0][0] > 0:
        chapters.insert(0, (0, "开场"))

    paras = merge_transcript(rows)
    by_chapter: Dict[int, List[Tuple[int, str]]] = {i: [] for i in range(len(chapters))}
    for para in paras:
        chapter_index = 0
        for i, (chapter_sec, _title) in enumerate(chapters):
            if para[0] >= chapter_sec:
                chapter_index = i
        by_chapter[chapter_index].append(para)

    transcript_blocks: List[str] = [
        "> [!info] 文字稿说明",
        "> 来源与整理方式见文末「提取状态」。若为 ASR 整理稿，**不是逐字稿**，人名、术语与数字引用前请核对原音频。",
        "",
    ]
    for i, (chapter_sec, chapter_title) in enumerate(chapters):
        transcript_blocks.append(f"### {format_timestamp(chapter_sec)} {chapter_title}")
        transcript_blocks.append("")
        for sec, text in by_chapter[i]:
            transcript_blocks.append(f"[{seconds_to_hms(sec)}] {text}")
            transcript_blocks.append("")
    transcript_body = "\n".join(transcript_blocks).strip() + "\n"

    chapter_body = "\n".join(
        f"- `{format_timestamp(sec)}` {chapter_title}" for sec, chapter_title in chapters
    )

    asr = meta.get("asr") or {}
    model = str(asr.get("model") or "")
    line_count = int(meta.get("quality", {}).get("line_count") or len(rows))
    if "asr" in resolver:
        method = f"ASR 提取（`faster-whisper` {model or 'small'}）"
    else:
        method = f"文字稿提取（`{resolver or 'unknown'}`）"
    status_body = "\n".join(
        [
            f"- {date.today().isoformat()}：{method}，共 {line_count} 个片段、约 {max(1, round(duration_sec / 60)) if duration_sec else 'N'} 分钟音频。",
            f"- 解析方式：`{resolver or 'unknown'}`。",
        ]
    )

    text = template
    text = _set_frontmatter(text, "created", _yaml(date.today().isoformat()))
    text = _set_frontmatter(text, "url", _yaml(url))
    text = _set_frontmatter(text, "title", _yaml(title))
    text = _set_frontmatter(text, "podcast", _yaml(podcast))
    text = _set_frontmatter(text, "host", _yaml(host))
    text = _set_frontmatter(text, "guest", _yaml(guest))
    text = _set_frontmatter(text, "published", published)
    text = _set_frontmatter(text, "duration", _yaml(duration))
    text = _set_frontmatter(text, "transcript_status", transcript_status)

    text = _set_inline(text, "podcast", podcast)
    text = _set_inline(text, "host", host)
    text = _set_inline(text, "guest", guest)
    text = _set_inline(text, "published", published)
    text = _set_inline(text, "duration", duration)
    text = re.sub(r"\[收听原节目\]\([^)]*\)", f"[收听原节目]({url})", text)

    text = _replace_section(text, "收听索引", chapter_body)
    text = _replace_section(text, "Transcript", transcript_body)
    text = _replace_section(text, "提取状态", status_body)
    # 模板里的 %% 使用说明只服务于模板本身，不进入成品笔记。
    text = re.sub(r"(?ms)^%%\n.*?^%%\n?", "", text)

    out_dir.mkdir(parents=True, exist_ok=True)
    existing = _existing_note(out_dir, url)
    if existing and not force:
        raise RuntimeError(f"note already exists for this URL: {existing} (use --force to overwrite)")

    date_prefix = published or date.today().isoformat()
    stem = f"{date_prefix} PODCAST"
    if podcast:
        stem += f" {podcast}"
    stem += f" - {title}"
    note_path = out_dir / f"{sanitize_filename(stem)}.md"
    if note_path.exists() and not force:
        raise RuntimeError(f"note path already exists: {note_path} (use --force to overwrite)")
    note_path.write_text(text, encoding="utf-8")
    return note_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an Obsidian podcast note from a transcript and meta.json")
    parser.add_argument("--txt", required=True, help="Transcript .txt path")
    parser.add_argument("--meta", required=True, help="Transcript .meta.json path")
    parser.add_argument("--template", required=True, help="Obsidian template path, e.g. Template/Podcast.md")
    parser.add_argument("--out-dir", required=True, help="Note output directory, e.g. Readwise/Podcast")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing note with the same URL")
    args = parser.parse_args()

    try:
        note = render_note_from_files(
            Path(args.txt), Path(args.meta), Path(args.template), Path(args.out_dir), args.force
        )
    except Exception as exc:
        print(f"FAIL\t{exc}", file=sys.stderr)
        return 1
    print(f"NOTE\t{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
