"""Normalize published tariffs and select a contiguous price-shifting plan."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class Tariff:
    start: float
    end: float
    price: float


@dataclass(frozen=True)
class PricePlan:
    charge: Tariff
    pause: Tariff
    saving_per_kwh: float
    energy_kwh: float | None
    defer: bool = False


def _timestamp(value):
    value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if value.utcoffset() is None:
        raise ValueError("Tariff timestamps must include a timezone")
    return value.timestamp()


def read_tariffs(attributes, config):
    """Accept known formats and configurable nested fields."""
    rows = attributes[config.get("forecast_attribute") or "forecast"]
    if not 1 <= len(rows) <= 3000:
        raise ValueError("Invalid forecast size")

    def field(row, path):
        for part in path.split("."):
            row = row[part]
        return row

    custom_price = config.get("price_field")
    parsed = []
    for row in rows:
        start = _timestamp(field(row, config.get("start_field") or "start_date"))
        end_field = config.get("end_field") or "end_date"
        try:
            end = _timestamp(field(row, end_field))
        except KeyError:
            if config.get("end_field"):
                raise
            end = start + 60 * config.get("interval_minutes", 60)
        price_field = custom_price or (
            "price_tax_included.amount" if "price_tax_included" in row else "electricity_price"
        )
        price = float(field(row, price_field)) / (config.get("price_scale", 1) if custom_price else 10_000_000)
        if not isfinite(price) or not 0 < end - start <= 3600 or abs(price) > 1000:
            raise ValueError("Invalid tariff interval or price")
        parsed.append(Tariff(start, end, price))
    parsed.sort(key=lambda row: row.start)
    if any(a.end > b.start for a, b in zip(parsed, parsed[1:])):
        raise ValueError("Overlapping tariff intervals")
    return tuple(parsed)


def choose_plan(rows, now, max_pause, minimum_spread, extra_energy, power_by_hour, allow_defer=False):
    """Rank contiguous block pairs using the estimated net cost per shifted kWh."""
    horizon = now + 86400
    clipped = []
    for row in rows:
        start = max(row.start, now)
        end = min(row.end, horizon)
        while start < end:
            boundary = min(end, (int(start // 900) + 1) * 900)
            clipped.append(Tariff(start, boundary, row.price))
            start = boundary
    rows = clipped
    charge = []
    pauses = []
    segment = 0
    for i, first in enumerate(rows):
        if i and rows[i - 1].end != first.start:
            segment += 1
        cost = 0.0
        end = first.start
        for row in rows[i:]:
            if row.start != end:
                break
            end = row.end
            seconds = end - first.start
            if seconds > max(max_pause, 10800):
                break
            cost += (row.end - row.start) * row.price
            if seconds < 1800:
                continue
            block = Tariff(first.start, end, cost / seconds)
            if seconds <= 10800:
                charge.append((segment, block))
            if seconds <= max_pause:
                pauses.append((segment, block))
    best = None
    best_score = 0.0
    for segment, pause in pauses:
        seconds = pause.end - pause.start
        power = power_by_hour.get(int(pause.start // 3600) % 24)
        energy = None if power is None else power * seconds / 3600000
        for other_segment, cheap in charge:
            defer = allow_defer and cheap.start == pause.end
            if (
                other_segment != segment
                or (not defer and not 0 <= pause.start - cheap.end <= 21600)
                or cheap.end - cheap.start < seconds
                or pause.price - cheap.price < minimum_spread
            ):
                continue
            saving = pause.price - cheap.price * (1 if defer else 1 + extra_energy)
            score = saving * (energy if energy is not None else seconds / 3600)
            if score > best_score:
                best_score = score
                best = PricePlan(cheap, pause, saving, energy, defer)
    return best
