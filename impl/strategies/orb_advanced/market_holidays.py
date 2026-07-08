"""
Holiday calendars for global exchanges used as liquidity proxies.

XAUUSD trades 24/5, but volatility is driven by institutional participation
during each region's cash equity session.  On exchange holidays the
corresponding "session" produces thinner, less reliable ORB breakouts.

Sources
-------
NYSE 2026 : https://www.nyse.com/trade/hours-calendars
JPX  2026 : https://www.jpx.co.jp/english/corporate/about-jpx/calendar/
LSE  2026 : https://www.londonstockexchange.com/trade/calendar
"""

from datetime import date


# ── NYSE (New York) ──────────────────────────────────────────────────────────
# US equities — proxy for NY-liquidity window (13:30-20:00 UTC).
# On these dates the NYSE is fully closed; XAUUSD spreads widen, volume drops.

NYSE_HOLIDAYS_2026: list[date] = [
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # Martin Luther King Jr. Day (3rd Mon Jan)
    date(2026, 2, 16),  # Washington's Birthday / Presidents' Day (3rd Mon Feb)
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day (last Mon May)
    date(2026, 6, 19),  # Juneteenth National Independence Day
    date(2026, 7, 3),   # Independence Day (observed Fri)
    date(2026, 9, 7),   # Labor Day (1st Mon Sep)
    date(2026, 11, 26), # Thanksgiving Day (4th Thu Nov)
    date(2026, 12, 25), # Christmas Day
]

# Early close 1:00 PM ET — ORB window may be truncated.
NYSE_EARLY_CLOSE_2026: list[date] = [
    date(2026, 11, 27), # Day after Thanksgiving
    date(2026, 12, 24), # Christmas Eve
]


# ── JPX (Tokyo) ──────────────────────────────────────────────────────────────
# Japanese equities — proxy for ASIA-liquidity window (00:00-09:00 UTC).
# Source: https://www.jpx.co.jp/english/corporate/about-jpx/calendar/
# JPX closes on national holidays plus Jan 2, Jan 3, Dec 31.

JPX_HOLIDAYS_2026: list[date] = [
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 2),   # Market Holiday
    date(2026, 1, 3),   # Market Holiday
    date(2026, 1, 12),  # Coming of Age Day (2nd Mon Jan)
    date(2026, 2, 11),  # National Foundation Day
    date(2026, 2, 23),  # Emperor's Birthday
    date(2026, 3, 20),  # Vernal Equinox
    date(2026, 4, 29),  # Showa Day
    date(2026, 5, 3),   # Constitution Memorial Day
    date(2026, 5, 4),   # Greenery Day
    date(2026, 5, 5),   # Children's Day
    date(2026, 5, 6),   # Constitution Memorial Day (May 3 observed)
    date(2026, 7, 20),  # Marine Day (3rd Mon Jul)
    date(2026, 8, 11),  # Mountain Day
    date(2026, 9, 21),  # Respect for the Aged Day (3rd Mon Sep)
    date(2026, 9, 22),  # Holiday (bridge)
    date(2026, 9, 23),  # Autumnal Equinox
    date(2026, 10, 12), # Sports Day (2nd Mon Oct)
    date(2026, 11, 3),  # Culture Day
    date(2026, 11, 23), # Labor Thanksgiving Day
    date(2026, 12, 31), # Market Holiday
]

# No early-close days on JPX (Night Session runs as usual).


# ── LSE (London) ─────────────────────────────────────────────────────────────
# UK equities — proxy for LONDON-liquidity window (07:00-16:00 UTC).
# Source: markethours.io/market-holidays/lse , marketbeat.com/stock-market-holidays/uk

LSE_HOLIDAYS_2026: list[date] = [
    date(2026, 1, 1),   # New Year's Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 6),   # Easter Monday
    date(2026, 5, 4),   # Early May Bank Holiday
    date(2026, 5, 25),  # Spring Bank Holiday
    date(2026, 8, 31),  # Summer Bank Holiday
    date(2026, 12, 25), # Christmas Day
    date(2026, 12, 28), # Boxing Day (observed)
]

LSE_EARLY_CLOSE_2026: list[date] = [
    date(2026, 12, 24), # Christmas Eve (closes 12:30)
    date(2026, 12, 31), # New Year's Eve (closes 12:30)
]


# ── Session-to-calendar mapping ──────────────────────────────────────────────
# Each entry is consumed by the strategy's SESSIONS config.
# Early-close lists are optional — the strategy can ignore them or use them
# to skip / truncate the ORB window.

SESSION_HOLIDAYS: dict[str, list[date]] = {
    "NY":     NYSE_HOLIDAYS_2026,
    "ASIA":   JPX_HOLIDAYS_2026,
    "LONDON": LSE_HOLIDAYS_2026,
}

SESSION_EARLY_CLOSE: dict[str, list[date]] = {
    "NY":     NYSE_EARLY_CLOSE_2026,
    "LONDON": LSE_EARLY_CLOSE_2026,
}
