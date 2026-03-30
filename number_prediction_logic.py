import random
from typing import Dict, List, Tuple


def build_recommendation(
    stats: Dict[str, List[int]], selected: List[int], ai_enabled: bool
) -> List[int]:
    selected_unique = sorted(set(selected))
    if not ai_enabled:
        return selected_unique
    if len(selected_unique) >= 7:
        return selected_unique
    top_3 = stats.get("top_3", [])
    bottom_3 = stats.get("bottom_3", [])
    middle_1 = stats.get("middle_1", [])
    base = list(dict.fromkeys(top_3 + bottom_3 + middle_1))
    base_set = set(base)
    missing = [number for number in selected_unique if number not in base_set]
    remove_needed = len(missing)
    if remove_needed == 0:
        return sorted(base)
    removal_candidates = middle_1 + sorted(bottom_3) + sorted(top_3)
    base_list = list(base)
    for candidate in removal_candidates:
        if remove_needed == 0:
            break
        if candidate in base_list and candidate not in selected_unique:
            base_list.remove(candidate)
            remove_needed -= 1
    if remove_needed:
        fallback = [num for num in sorted(base_list) if num not in selected_unique]
        for candidate in fallback:
            if remove_needed == 0:
                break
            if candidate in base_list:
                base_list.remove(candidate)
                remove_needed -= 1
    base_list.extend(missing)
    return sorted(dict.fromkeys(base_list))[:7]


def ai_base_numbers(stats: Dict[str, List[int]]) -> List[int]:
    top_3 = stats.get("top_3", [])
    bottom_3 = stats.get("bottom_3", [])
    middle_1 = stats.get("middle_1", [])
    return sorted(set(top_3 + bottom_3 + middle_1))


def generate_history_prediction(
    code: str, digits: Tuple[int, int, int], accuracy: float = 0.95
) -> Dict[str, List[int]]:
    seed_value = int(code) if code.isdigit() else sum(ord(ch) for ch in code)
    rng = random.Random(seed_value)
    positions = ["hundreds_place", "tens_place", "units_place"]
    incorrect_position = None
    if rng.random() >= accuracy:
        incorrect_position = rng.choice(positions)
    return {
        "hundreds_place": _generate_position_numbers(
            digits[0], incorrect_position != "hundreds_place", rng
        ),
        "tens_place": _generate_position_numbers(
            digits[1], incorrect_position != "tens_place", rng
        ),
        "units_place": _generate_position_numbers(
            digits[2], incorrect_position != "units_place", rng
        ),
    }


def _generate_position_numbers(
    actual_digit: int, include_actual: bool, rng: random.Random
) -> List[int]:
    available = [digit for digit in range(10) if digit != actual_digit]
    if include_actual:
        picks = rng.sample(available, 6)
        return sorted([actual_digit] + picks)
    return sorted(rng.sample(available, 7))


def numbers_to_text(numbers: List[int]) -> str:
    return ",".join(str(number) for number in numbers)
