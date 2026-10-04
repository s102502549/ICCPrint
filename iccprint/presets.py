"""Typed, bounded local settings; presets never carry driver acknowledgements."""
from __future__ import annotations

import math

from .color import INTENTS
from .printing import PAPER_SIZES_MM

DEFAULTS = {
    "intent": "相對比色 (Relative Colorimetric)", "bpc": True, "dpi": 300,
    "fallback_dpi": 300, "scale": "fit", "paper": "A4 (210 × 297 mm)",
    "orientation": "portrait", "custom_w_mm": 210.0, "custom_h_mm": 297.0,
    "profile": "",
}
NUMERIC = {"dpi": (150, 600, int), "fallback_dpi": (36, 2400, int),
           "custom_w_mm": (50, 500, float), "custom_h_mm": (50, 700, float)}
CHOICES = {"intent": INTENTS, "paper": PAPER_SIZES_MM,
           "scale": ("fit", "fill", "actual"), "orientation": ("portrait", "landscape")}


def validate_value(key, value):
    if key not in DEFAULTS:
        raise ValueError(f"未知的預設欄位：{key}")
    if key in NUMERIC:
        low, high, kind = NUMERIC[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} 必須是數字。")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} 必須是數字。") from exc
        if not math.isfinite(number) or not low <= number <= high or (kind is int and not number.is_integer()):
            raise ValueError(f"{key} 必須介於 {low}–{high}。")
        return kind(number)
    if key == "bpc":
        if value is True or value == "true":
            return True
        if value is False or value == "false":
            return False
        raise ValueError("bpc 必須是布林值。")
    if not isinstance(value, str):
        raise ValueError(f"{key} 必須是文字。")
    if key in CHOICES and value not in CHOICES[key]:
        raise ValueError(f"{key} 不是可用選項。")
    if key == "profile" and (len(value) > 32768 or "\x00" in value):
        raise ValueError("ICC 路徑無效。")
    return value


def normalize_preset(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("預設內容不是有效的設定物件。")
    return {key: validate_value(key, value.get(key, default)) for key, default in DEFAULTS.items()}
