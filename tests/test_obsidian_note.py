import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "obsidian_note.py"
SPEC = importlib.util.spec_from_file_location("obsidian_note", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class NoteParserTests(unittest.TestCase):
    def test_parse_chapters_skips_nested_earlier_timestamp(self) -> None:
        text = """【时光机】
* 01:26 项目介绍
* 02:20 决策很便宜
  * 01:50 子条目
* 04:35 可验证通道
"""
        self.assertEqual(
            MODULE.parse_chapters(text),
            [(86, "项目介绍"), (140, "决策很便宜"), (275, "可验证通道")],
        )

    def test_format_timestamp(self) -> None:
        self.assertEqual(MODULE.format_timestamp(86), "01:26")
        self.assertEqual(MODULE.format_timestamp(3723), "01:02:03")

    def test_merge_transcript_keeps_timestamps_and_caps_length(self) -> None:
        rows = [(i * 2, "这是一段测试文本" * 3) for i in range(20)]
        paras = MODULE.merge_transcript(rows, max_chars=60)
        self.assertGreater(len(paras), 1)
        self.assertTrue(all(len(text) <= 120 for _sec, text in paras))
        self.assertEqual(paras[0][0], 0)

    def test_replace_section_only_touches_target(self) -> None:
        template = "## Summary\n\nold\n\n## Transcript\n\nold transcript\n\n## 提取状态\n\nold status\n"
        out = MODULE._replace_section(template, "Transcript", "### 00:00 开场\n\nnew")
        self.assertIn("## Summary\n\nold", out)
        self.assertIn("### 00:00 开场\n\nnew", out)
        self.assertIn("## 提取状态", out)
        self.assertNotIn("old transcript", out)


if __name__ == "__main__":
    unittest.main()
