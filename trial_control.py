from datetime import date, timedelta
from typing import Optional

TRIAL_START_DATE: Optional[str] = "2026-03-30"
TRIAL_DAYS = 7


def get_trial_start_date(today: Optional[date] = None) -> date:
    base_date = today or date.today()
    if TRIAL_START_DATE:
        return date.fromisoformat(TRIAL_START_DATE)
    return base_date + timedelta(days=0)


def is_trial_active(today: Optional[date] = None) -> bool:
    base_date = today or date.today()
    start_date = get_trial_start_date(base_date)
    end_date = start_date + timedelta(days=TRIAL_DAYS)
    return start_date <= base_date < end_date


def get_trial_status(today: Optional[date] = None) -> str:
    base_date = today or date.today()
    start_date = get_trial_start_date(base_date)
    end_date = start_date + timedelta(days=TRIAL_DAYS)
    if base_date < start_date:
        remaining = (end_date - start_date).days
        return f"试用期未开始（将开始于 {start_date.isoformat()}，共 {remaining} 天）"
    if base_date >= end_date:
        return "试用期已结束"
    remaining = (end_date - base_date).days
    return f"试用期剩余 {remaining} 天"
