"""
scheduler_inputs.py
-------------------
Custom Streamlit input components for the ATL01 thermal model job scheduler.
Single flat module — no package, no __init__.py, no namespace conflicts.

All three inputs share one declare_component and one theme file:
    scheduler_inputs_frontend/theme.js  ← edit here to restyle everything

Usage in thermal_model_streamlit.py:
    from scheduler_inputs import (
        clock_time_input,
        duration_time_input,
        gpu_power_input,
        duration_to_hours,
    )
"""

import os
import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scheduler_inputs",
)

_component_func = components.declare_component(
    name="scheduler_inputs",
    path=_FRONTEND_DIR,
)


# ── Public input functions ────────────────────────────────────────────────────

def clock_time_input(label: str = "Start Time",
                     default: str = None,
                     key: str = None):
    """
    24-hour digital clock input with shift-left digit entry.
    Shows 'hh:mm' placeholder until the user types the first digit.
    Returns "HH:MM" string once touched, None while showing placeholder.
    """
    result = _component_func(
        type="clock",
        label=label,
        hint="Enter 24-hour time",
        key=key,
        default=default,
    )
    return result if _is_valid_hhmm(result, max_hours=23) else None


def duration_time_input(label: str = "Duration",
                        default: str = None,
                        key: str = None):
    """
    Duration input with shift-left digit entry.
    Shows 'hh:mm' placeholder until the user types the first digit.
    Snaps to nearest 30 minutes on blur.
    Returns "HH:MM" string once touched, None while showing placeholder.
    Convert to float hours using duration_to_hours().
    """
    result = _component_func(
        type="duration",
        label=label,
        hint="Snaps to nearest 30 min, max 24:00 time",
        snap=30,
        key=key,
        default=default,
    )
    return result if _is_valid_hhmm(result, max_hours=24) else None


def gpu_power_input(label: str = "GPU Power Level",
                    options: list = None,
                    default: str = "Medium (40 kW)",
                    key: str = None) -> str:
    """
    Styled dropdown for GPU power level selection.
    Returns the selected option string.
    """
    if options is None:
        options = ["Low (20 kW)", "Medium (40 kW)", "High (55 kW)"]
    result = _component_func(
        type="gpu",
        label=label,
        options=options,
        initial=default,
        key=key,
        default=default,
    )
    return result if isinstance(result, str) and result in options else default


def rack_count_input(label: str = "Number of Racks",
                     default: int = 10,
                     min_racks: int = 1,
                     max_racks: int = 60,
                     key: str = None) -> int:
    """
    Styled rack count input with +/- buttons and inline error state.

    Dynamically enforces min/max — pass total_available_racks as max_racks
    and the component will re-validate on every Streamlit rerun.

    Returns an int. When the value is out of bounds the component shows
    an error state but still returns the current (invalid) value so the
    caller can decide whether to disable the Add Job button.

    Use rack_count_valid() to check before enabling the button.
    """
    result = _component_func(
        type="rack_count",
        label=label,
        initial=str(default),
        min_racks=min_racks,
        max_racks=max_racks,
        key=key,
        default=default,
    )
    try:
        return int(result)
    except (TypeError, ValueError):
        return default


def rack_count_valid(value: int, min_racks: int = 1, max_racks: int = 60) -> bool:
    """Return True if the rack count value is within the allowed range."""
    return min_racks <= value <= max_racks


# ── Utilities ─────────────────────────────────────────────────────────────────

def duration_to_hours(hhmm: str) -> float:
    """Convert "HH:MM" duration string to float hours. e.g. "02:30" → 2.5"""
    try:
        hh, mm = map(int, hhmm.split(":"))
        return hh + mm / 60.0
    except (ValueError, AttributeError):
        return 2.0


def hours_to_duration(hours: float) -> str:
    """Convert float hours to "HH:MM" string. e.g. 2.5 → "02:30" """
    total_minutes = round(hours * 60)
    hh = total_minutes // 60
    mm = total_minutes % 60
    return f"{min(hh, 24):02d}:{mm:02d}"


# ── Internal ──────────────────────────────────────────────────────────────────

def _is_valid_hhmm(value, max_hours: int = 23) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        hh, mm = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 0 <= hh <= max_hours and 0 <= mm <= 59