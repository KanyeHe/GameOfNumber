import json
import sqlite3
from http.cookiejar import CookieJar
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app_logging import get_logger
from prediction_updater import update_pending_predictions

DEFAULT_URL = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
)


@dataclass(frozen=True)
class DrawRecord:
    name: str
    code: str
    date: str
    red: str
    hundreds_place: int
    tens_place: int
    units_place: int


@dataclass(frozen=True)
class PredictionRecord:
    code: str
    red: str
    status: str
    danma_selection: str
    ai_hundreds: str
    ai_tens: str
    ai_units: str
    hundreds_dan: str
    tens_dan: str
    units_dan: str


class LotteryStorage:
    def __init__(self, db_path: str = "lottery.db") -> None:
        self.db_path = db_path
        self._cookie_jar = CookieJar()
        self._logger = get_logger()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS draw_results (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    red TEXT NOT NULL,
                    hundreds_place INTEGER NOT NULL,
                    tens_place INTEGER NOT NULL,
                    units_place INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_records (
                    code TEXT PRIMARY KEY,
                    red TEXT NOT NULL,
                    status TEXT NOT NULL,
                    danma_selection TEXT NOT NULL,
                    ai_recommendation TEXT NOT NULL,
                    ai_hundreds TEXT NOT NULL,
                    ai_tens TEXT NOT NULL,
                    ai_units TEXT NOT NULL,
                    hundreds_dan TEXT NOT NULL,
                    tens_dan TEXT NOT NULL,
                    units_dan TEXT NOT NULL
                )
                """
            )
            self._ensure_prediction_schema(conn)
            conn.commit()

    def _ensure_prediction_schema(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(prediction_records)")
        columns = {row[1] for row in cursor.fetchall()}
        additions = [
            ("ai_hundreds", "TEXT NOT NULL DEFAULT ''"),
            ("ai_tens", "TEXT NOT NULL DEFAULT ''"),
            ("ai_units", "TEXT NOT NULL DEFAULT ''"),
        ]
        for column, definition in additions:
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE prediction_records ADD COLUMN {column} {definition}"
                )

    def fetch_draws(
        self, page_no: int = 1, page_size: int = 30, url: str = DEFAULT_URL
    ) -> List[DrawRecord]:
        params = (
            f"name=3d&issueCount=&issueStart=&issueEnd=&dayStart=&dayEnd="
            f"&pageNo={page_no}&pageSize={page_size}&week=&systemType=PC"
        )
        request = Request(
            f"{url}?{params}",
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
                "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/fc3d/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "X-Requested-With": "XMLHttpRequest",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", '
                '"Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            },
        )
        opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result", [])
        records: List[DrawRecord] = []
        for item in result:
            red = item.get("red", "")
            digits = self._split_red(red)
            if digits is None:
                continue
            records.append(
                DrawRecord(
                    name=item.get("name", ""),
                    code=str(item.get("code", "")),
                    date=item.get("date", ""),
                    red=red,
                    hundreds_place=digits[0],
                    tens_place=digits[1],
                    units_place=digits[2],
                )
            )
        return records

    def _split_red(self, red: str) -> Optional[Tuple[int, int, int]]:
        parts = [value.strip() for value in red.split(",")]
        if len(parts) != 3:
            return None
        try:
            digits = tuple(int(value) for value in parts)
        except ValueError:
            return None
        if any(digit < 0 or digit > 9 for digit in digits):
            return None
        return digits  # type: ignore[return-value]

    def save_records(self, records: Iterable[DrawRecord]) -> int:
        rows = list(records)
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO draw_results (
                    code,
                    name,
                    date,
                    red,
                    hundreds_place,
                    tens_place,
                    units_place
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.code,
                        row.name,
                        row.date,
                        row.red,
                        row.hundreds_place,
                        row.tens_place,
                        row.units_place,
                    )
                    for row in rows
                ],
            )
            conn.commit()
        return len(rows)

    def sync_latest_draws(self, max_pages: int = 5) -> int:
        total = 0
        for page in range(1, max_pages + 1):
            records = self.fetch_draws(page_no=page)
            if not records:
                break
            total += self.save_records(records)
            if len(records) < 30:
                break
        self._ensure_prediction_rows()
        self._update_pending_predictions()
        return total

    def get_latest_records(self, limit: int = 48) -> List[DrawRecord]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT name, code, date, red, hundreds_place, tens_place, units_place
                FROM draw_results
                ORDER BY date DESC, code DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            DrawRecord(
                name=row[0],
                code=row[1],
                date=row[2],
                red=row[3],
                hundreds_place=row[4],
                tens_place=row[5],
                units_place=row[6],
            )
            for row in rows
        ]

    def get_latest_code(self) -> Optional[str]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT code
                FROM draw_results
                ORDER BY date DESC, code DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def get_next_code(self) -> Optional[str]:
        latest = self.get_latest_code()
        if latest is None:
            return None
        if latest.isdigit():
            return str(int(latest) + 1).zfill(len(latest))
        return f"{latest}_next"

    def get_stats_for_latest(self, limit: int = 48) -> Dict[str, Dict[str, List[int]]]:
        records = self.get_latest_records(limit=limit)
        positions = {
            "hundreds_place": [record.hundreds_place for record in records],
            "tens_place": [record.tens_place for record in records],
            "units_place": [record.units_place for record in records],
        }
        return {
            position: self._calculate_stats(values) for position, values in positions.items()
        }

    def _calculate_stats(self, values: List[int]) -> Dict[str, List[int]]:
        counts = {digit: 0 for digit in range(10)}
        for value in values:
            if value in counts:
                counts[value] += 1
        sorted_by_high = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        sorted_by_low = sorted(counts.items(), key=lambda item: (item[1], item[0]))
        top_3 = [digit for digit, _ in sorted_by_high[:3]]
        bottom_3: List[int] = []
        for digit, _ in sorted_by_low:
            if digit not in top_3:
                bottom_3.append(digit)
            if len(bottom_3) == 3:
                break
        remaining = [
            digit
            for digit, _ in sorted_by_low
            if digit not in top_3 and digit not in bottom_3
        ]
        mid_index = len(remaining) // 2
        middle_1 = [remaining[mid_index]] if remaining else [top_3[-1]]
        return {"top_3": top_3, "bottom_3": bottom_3, "middle_1": middle_1}

    def get_prediction_records(self) -> List[PredictionRecord]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    code,
                    red,
                    status,
                    danma_selection,
                    ai_hundreds,
                    ai_tens,
                    ai_units,
                    hundreds_dan,
                    tens_dan,
                    units_dan
                FROM prediction_records
                ORDER BY code DESC
                """
            )
            rows = cursor.fetchall()
        return [
            PredictionRecord(
                code=row[0],
                red=row[1],
                status=row[2],
                danma_selection=row[3],
                ai_hundreds=row[4],
                ai_tens=row[5],
                ai_units=row[6],
                hundreds_dan=row[7],
                tens_dan=row[8],
                units_dan=row[9],
            )
            for row in rows
        ]

    def upsert_pending_prediction(
        self,
        code: str,
        danma_selection: str,
        ai_hundreds: str,
        ai_tens: str,
        ai_units: str,
        hundreds_dan: str,
        tens_dan: str,
        units_dan: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM prediction_records WHERE status = '待开奖' AND code != ?",
                (code,),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO prediction_records (
                    code,
                    red,
                    status,
                    danma_selection,
                    ai_recommendation,
                    ai_hundreds,
                    ai_tens,
                    ai_units,
                    hundreds_dan,
                    tens_dan,
                    units_dan
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    "",
                    "待开奖",
                    danma_selection,
                    "",
                    ai_hundreds,
                    ai_tens,
                    ai_units,
                    hundreds_dan,
                    tens_dan,
                    units_dan,
                ),
            )
            conn.commit()

    def update_prediction_values(
        self, code: str, hundreds_dan: str, tens_dan: str, units_dan: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE prediction_records
                SET hundreds_dan = ?, tens_dan = ?, units_dan = ?
                WHERE code = ?
                """,
                (hundreds_dan, tens_dan, units_dan, code),
            )
            conn.commit()

    def _ensure_prediction_rows(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO prediction_records (
                    code,
                    red,
                    status,
                    danma_selection,
                    ai_recommendation,
                    ai_hundreds,
                    ai_tens,
                    ai_units,
                    hundreds_dan,
                    tens_dan,
                    units_dan
                )
                SELECT
                    code,
                    red,
                    '已开奖',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    ''
                FROM draw_results
                """
            )
            conn.execute(
                """
                UPDATE prediction_records
                SET red = (
                        SELECT red
                        FROM draw_results
                        WHERE draw_results.code = prediction_records.code
                    ),
                    status = '已开奖'
                WHERE EXISTS (
                    SELECT 1
                    FROM draw_results
                    WHERE draw_results.code = prediction_records.code
                )
                """
            )
            conn.commit()

    def _update_pending_predictions(self) -> None:
        with self._connect() as conn:
            update_pending_predictions(conn)

    def get_by_code(self, code: str) -> Optional[DrawRecord]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT name, code, date, red, hundreds_place, tens_place, units_place
                FROM draw_results
                WHERE code = ?
                """,
                (code,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return DrawRecord(
            name=row[0],
            code=row[1],
            date=row[2],
            red=row[3],
            hundreds_place=row[4],
            tens_place=row[5],
            units_place=row[6],
        )
