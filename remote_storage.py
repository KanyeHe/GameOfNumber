from typing import Dict, List, Optional

from central_api import CentralApiClient
from lottery_storage import DrawRecord, PredictionRecord


class RemoteLotteryStorage:
    def __init__(self, api_client: CentralApiClient) -> None:
        self.api = api_client

    def sync_latest_draws(self, max_pages: int = 5) -> int:
        records = self.api.list_draws(limit=max_pages * 10)
        return len(records)

    def get_latest_records(self, limit: int = 48) -> List[DrawRecord]:
        rows = self.api.list_draws(limit=limit)
        return [self._to_draw_record(row) for row in rows]

    def get_latest_code(self) -> Optional[str]:
        records = self.get_latest_records(limit=1)
        return records[0].code if records else None

    def get_next_code(self) -> Optional[str]:
        latest = self.get_latest_code()
        if latest is None:
            return None
        if latest.isdigit():
            return str(int(latest) + 1).zfill(len(latest))
        return f"{latest}_next"

    def get_stats_for_recent_days(self, days: int = 21) -> Dict[str, Dict[str, List[int]]]:
        payload = self.api.get_recent_stats(days=days)
        data = payload.get("data", payload)
        return data if isinstance(data, dict) else {}

    def get_prediction_records(self) -> List[PredictionRecord]:
        rows = self.api.list_predictions(limit=50)
        return [self._to_prediction_record(row) for row in rows]

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
        self.api.save_prediction(
            {
                "code": code,
                "status": "PENDING",
                "danmaSelection": danma_selection,
                "aiHundreds": ai_hundreds,
                "aiTens": ai_tens,
                "aiUnits": ai_units,
                "hundredsDan": hundreds_dan,
                "tensDan": tens_dan,
                "unitsDan": units_dan,
            }
        )

    def update_prediction_values(
        self, code: str, hundreds_dan: str, tens_dan: str, units_dan: str
    ) -> None:
        self.api.update_prediction_verification(
            code,
            {
                "hundredsDan": hundreds_dan,
                "tensDan": tens_dan,
                "unitsDan": units_dan,
            },
        )

    def get_by_code(self, code: str) -> Optional[DrawRecord]:
        payload = self.api.get_draw_by_code(code)
        data = payload.get("data", payload)
        if not isinstance(data, dict) or not data:
            return None
        return self._to_draw_record(data)

    def _to_draw_record(self, row: Dict[str, object]) -> DrawRecord:
        red = str(row.get("red", ""))
        digits = [part.strip() for part in red.split(",")]
        return DrawRecord(
            name=str(row.get("name", "")),
            code=str(row.get("code", "")),
            date=str(row.get("date", "")),
            red=red,
            hundreds_place=int(row.get("hundredsPlace", digits[0] if len(digits) > 0 else 0)),
            tens_place=int(row.get("tensPlace", digits[1] if len(digits) > 1 else 0)),
            units_place=int(row.get("unitsPlace", digits[2] if len(digits) > 2 else 0)),
        )

    def _to_prediction_record(self, row: Dict[str, object]) -> PredictionRecord:
        status = str(row.get("status", ""))
        status_mapping = {"PENDING": "待开奖", "RESOLVED": "已开奖"}
        return PredictionRecord(
            code=str(row.get("code", "")),
            red=str(row.get("red", "")),
            status=status_mapping.get(status, status),
            danma_selection=str(row.get("danmaSelection", "")),
            ai_hundreds=str(row.get("aiHundreds", "")),
            ai_tens=str(row.get("aiTens", "")),
            ai_units=str(row.get("aiUnits", "")),
            hundreds_dan=str(row.get("hundredsDan", "")),
            tens_dan=str(row.get("tensDan", "")),
            units_dan=str(row.get("unitsDan", "")),
        )
