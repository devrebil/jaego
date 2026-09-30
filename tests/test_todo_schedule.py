# PRO·FREE 투두의 날짜·시간 해석과 지정 날짜 저장을 검증하는 테스트
from __future__ import annotations

import ast
import copy
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ("PRO", "FREE")
PARSER_NAMES = {
    "TODO_KOREAN_HOURS",
    "TODO_HOUR_PATTERN",
    "_todo_clock_match",
    "_todo_deadline_end",
    "_schedule_from_todo",
}


def load_todo_contract(edition: str):
    source_path = ROOT / edition / "app.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    nodes = []
    for source_node in tree.body:
        node = copy.deepcopy(source_node)
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & PARSER_NAMES:
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in PARSER_NAMES:
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "api_calendar_todos_save":
            node.decorator_list = []
            nodes.append(node)

    namespace = {
        "re": re,
        "datetime": datetime,
        "timedelta": timedelta,
    }
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace


class TodoScheduleParserTest(unittest.TestCase):
    def test_supported_date_and_time_phrases(self):
        expected_cases = {
            "07/17 점심식사": ("2026-07-17", "2026-07-17", "", "", "점심식사"),
            "17일 8시에 약속": ("2026-07-17", "2026-07-17", "08:00", "09:00", "약속"),
            "7월 15일 9시부터10시까지 회의": ("2026-07-15", "2026-07-15", "09:00", "10:00", "회의"),
            "07-15 09시~10시 회의": ("2026-07-15", "2026-07-15", "09:00", "10:00", "회의"),
            "07/15 09:00~10:00 회의": ("2026-07-15", "2026-07-15", "09:00", "10:00", "회의"),
            "아홉시까지 보고": ("2026-07-16", "2026-07-16", "08:30", "09:00", "보고"),
            "12시까지 제출": ("2026-07-16", "2026-07-16", "08:30", "12:00", "제출"),
            "09:00 출근": ("2026-07-16", "2026-07-16", "09:00", "10:00", "출근"),
        }
        now = datetime(2026, 7, 16, 8, 30)
        for edition in EDITIONS:
            parse = load_todo_contract(edition)["_schedule_from_todo"]
            for content, expected in expected_cases.items():
                with self.subTest(edition=edition, content=content):
                    result = parse(content, "2026-07-16", now)
                    actual = (
                        result["start_date"], result["end_date"], result["start_time"],
                        result["end_time"], result["title"],
                    )
                    self.assertEqual(actual, expected)

            self.assertIsNone(parse("일반 할 일", "2026-07-16", now))
            self.assertIsNone(parse("02/30 잘못된 날짜", "2026-07-16", now))
            self.assertIsNone(parse("32일 잘못된 날짜", "2026-07-16", now))
            self.assertIsNone(parse("17일간 작업", "2026-07-16", now))
            self.assertIsNone(parse("7월 17일간 작업", "2026-07-16", now))
            self.assertIsNone(parse("8시간 작업", "2026-07-16", now))
            self.assertIsNone(parse("8시에너지 연구", "2026-07-16", now))

    def test_korean_deadline_uses_next_upcoming_hour(self):
        now = datetime(2026, 7, 16, 10, 15)
        for edition in EDITIONS:
            parse = load_todo_contract(edition)["_schedule_from_todo"]
            result = parse("아홉시까지 마감", "2026-07-16", now)
            self.assertEqual((result["start_time"], result["end_time"]), ("10:15", "21:00"))

    def test_api_saves_todo_on_parsed_date(self):
        for edition in EDITIONS:
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "calendar.db"
                conn = sqlite3.connect(db_path)
                conn.executescript("""
                    CREATE TABLE daily_todos(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user TEXT, date TEXT, content TEXT, done INTEGER DEFAULT 0, created_at TEXT
                    );
                    CREATE TABLE schedules(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT, start_date TEXT, end_date TEXT,
                        start_time TEXT, end_time TEXT, memo TEXT, status TEXT,
                        author TEXT, created_at TEXT, color TEXT
                    );
                """)
                conn.close()

                namespace = load_todo_contract(edition)

                def get_db(_domain):
                    connection = sqlite3.connect(db_path)
                    connection.row_factory = sqlite3.Row
                    return connection

                namespace.update({
                    "request": SimpleNamespace(json={"date": "2026-07-16", "content": "17일 8시에 약속"}),
                    "get_db": get_db,
                    "cur_user": lambda: "tester",
                    "now_str": lambda: "2026-07-16 08:30:00",
                    "jsonify": lambda **values: values,
                })
                response = namespace["api_calendar_todos_save"]()

                conn = sqlite3.connect(db_path)
                todo = conn.execute("SELECT date,content FROM daily_todos").fetchone()
                schedule = conn.execute(
                    "SELECT start_date,end_date,start_time,end_time,title FROM schedules"
                ).fetchone()
                conn.close()

                self.assertEqual(response["todo_date"], "2026-07-17")
                self.assertEqual(todo, ("2026-07-17", "17일 8시에 약속"))
                self.assertEqual(
                    schedule,
                    ("2026-07-17", "2026-07-17", "08:00", "09:00", "약속"),
                )


if __name__ == "__main__":
    unittest.main()
