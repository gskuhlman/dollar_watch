"""Streamlit/Arrow-safe formatting for fixed-horizon display tables.

A column must not contain both Python floats and string N/A, because Arrow
will try to coerce N/A into a float. Return consistent strings for every cell
in the optional-value columns; this does not alter numeric scores in SQLite.
"""
from __future__ import annotations

import math


def optional_number_text(value: object, decimals: int = 2, signed: bool = False) -> str:
    """Format optional display numbers as strings; never mix numeric/str cells."""
    if value is None or isinstance(value, bool):
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "N/A"
    if not math.isfinite(number):
        return "N/A"
    return f"{number:+.{decimals}f}" if signed else f"{number:.{decimals}f}"
