# PRO·FREE 독립 HTML 사용설명서의 목차와 핵심 안내 문구를 검증한다.
from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANUALS = {
    "PRO": ROOT / "PRO_사용설명서.html",
    "FREE": ROOT / "FREE_사용설명서.html",
}


class ManualStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.local_links: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href", "").startswith("#"):
            self.local_links.append(values["href"][1:])


class ManualTest(unittest.TestCase):
    def test_manual_navigation_and_unique_ids(self):
        for edition, path in MANUALS.items():
            with self.subTest(edition=edition):
                source = path.read_text(encoding="utf-8")
                parser = ManualStructureParser()
                parser.feed(source)
                self.assertEqual(len(parser.ids), len(set(parser.ids)))
                self.assertFalse(set(parser.local_links) - set(parser.ids))

    def test_new_todo_and_settings_guidance_is_present(self):
        common_phrases = (
            "17일 8시에 약속",
            "7월 17일",
            "08:00~09:00",
            "0건",
            "홈 매입",
            "사용자별 서버",
            "브라우저",
            "완전 초기화",
            "자동 백업",
        )
        for edition, path in MANUALS.items():
            with self.subTest(edition=edition):
                source = path.read_text(encoding="utf-8")
                for phrase in common_phrases:
                    self.assertIn(phrase, source, phrase)

        self.assertIn("멀티 검색", MANUALS["PRO"].read_text(encoding="utf-8"))
        self.assertIn("FREE에서 백업할 수 있는 6개 DB", MANUALS["FREE"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
