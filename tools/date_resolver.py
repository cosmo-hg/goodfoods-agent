"""
Deterministic date resolver.

The LLM was being asked to do date math ("today is 2026-06-04, what is 'this
Saturday'?"). Small models get this wrong; even large ones sometimes pick the
wrong weekday. Production fix: pre-compute the next 14 days with day names
and known relative phrases, hand the table to the LLM in user_context. The
LLM stops calculating and starts looking up.

This module is pure Python — no LLM calls, no external services, no API keys.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional


_WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _next_weekday(base: _dt.date, target_weekday: int, *, this_week_ok: bool = True) -> _dt.date:
    """
    Return the next date with the given weekday (0=Mon … 6=Sun).

    If this_week_ok is True and `base.weekday() == target_weekday`, returns
    base itself (today). If this_week_ok is False, always skips at least 1 day.
    """
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0 and not this_week_ok:
        days_ahead = 7
    return base + _dt.timedelta(days=days_ahead)


def build_date_reference(today: Optional[_dt.date] = None) -> dict:
    """
    Build a reference table of common relative-date phrases → ISO dates.

    Returns:
      {
        "today_iso":       "2026-06-04",
        "today_weekday":   "Thursday",
        "phrases":         {"today": "...", "tomorrow": "...", ...},
        "next_14_days":    [(iso, weekday), ...]   # ordered chronologically
      }
    """
    base = today or _dt.date.today()
    phrases: dict[str, str] = {
        "today":               base.isoformat(),
        "tomorrow":            (base + _dt.timedelta(days=1)).isoformat(),
        "day after tomorrow":  (base + _dt.timedelta(days=2)).isoformat(),
    }

    # "This <weekday>" — the next occurrence including today
    # "Next <weekday>" — exactly 7 days after "this <weekday>". Always one week
    # later, regardless of which day of the week it is today. This matches
    # everyday usage: said on Thursday, "next Saturday" is the Saturday a week
    # after the upcoming one.
    for i, name in enumerate(_WEEKDAY_NAMES):
        this_one = _next_weekday(base, i, this_week_ok=True)
        next_one = this_one + _dt.timedelta(days=7)
        # Slight nuance: when the day-name appears alone ("Saturday"), most
        # guests mean the upcoming one — which is `this <name>`.
        phrases[name.lower()] = this_one.isoformat()
        phrases[f"this {name.lower()}"] = this_one.isoformat()
        phrases[f"next {name.lower()}"] = next_one.isoformat()

    # Weekend variants — most often guests mean the upcoming Saturday/Sunday
    upcoming_sat = _next_weekday(base, 5, this_week_ok=True)
    upcoming_sun = _next_weekday(base, 6, this_week_ok=True)
    phrases["weekend"]      = upcoming_sat.isoformat()        # default to Sat
    phrases["this weekend"] = upcoming_sat.isoformat()
    phrases["next weekend"] = (upcoming_sat + _dt.timedelta(days=7)).isoformat()

    # Next 14 days for a compact, model-readable table
    next_14 = [
        ((base + _dt.timedelta(days=d)).isoformat(),
         _WEEKDAY_NAMES[(base + _dt.timedelta(days=d)).weekday()])
        for d in range(14)
    ]

    return {
        "today_iso":     base.isoformat(),
        "today_weekday": _WEEKDAY_NAMES[base.weekday()],
        "phrases":       phrases,
        "next_14_days":  next_14,
    }


def format_for_llm(today: Optional[_dt.date] = None) -> str:
    """
    Render the date reference as a single short line for user_context.

    The LLM sees something like:
      [Today: 2026-06-04 (Thursday). Relative dates:
       today=2026-06-04, tomorrow=2026-06-05, saturday=2026-06-06,
       sunday=2026-06-07, monday=2026-06-08, next saturday=2026-06-13,
       weekend=2026-06-06. Always pass ISO YYYY-MM-DD to tools.]
    """
    ref = build_date_reference(today)
    keys = [
        "today", "tomorrow",
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
        "next saturday", "next sunday",
        "weekend", "next weekend",
    ]
    pairs = ", ".join(f"{k}={ref['phrases'][k]}" for k in keys if k in ref["phrases"])
    return (
        f"[Today: {ref['today_iso']} ({ref['today_weekday']}). "
        f"Relative date lookup: {pairs}. "
        f"When a guest uses a relative phrase, look it up here and pass the ISO "
        f"date verbatim to tools. Never compute dates yourself.]"
    )
