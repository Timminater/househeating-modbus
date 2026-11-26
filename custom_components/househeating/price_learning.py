"""Learn a preheating energy estimate from completed, comparable price windows."""

from math import ceil, floor
from statistics import median

SLOT = 900
RETENTION = 28 * 86400
RECOVERY = 7200


class PriceEnergyLearning:
    def __init__(self):
        self.previous = None
        self.bucket = None

    @staticmethod
    def estimate(data):
        results = data.get("results", [])
        shifted = sum(row[1] for row in results)
        extra = sum(row[2] for row in results)
        percentage = 100 * extra / shifted if shifted and len(results) >= 3 else None
        return {
            "percentage": None if percentage is None else round(min(100, max(0, percentage)), 1),
            "observed_percentage": None if percentage is None else round(percentage, 1),
            "sample_count": len(results),
            "shifted_kwh": round(shifted, 3),
            "extra_kwh": round(extra, 3),
        }

    def sample(self, data, now, watts, outdoor, clean):
        """Integrate power over complete quarters. Discard gaps and partial quarters."""
        previous = self.previous
        self.previous = None if watts is None or outdoor is None else (now, watts, outdoor, clean)
        if previous is None or self.previous is None or not 0 < now - previous[0] <= 90:
            self.bucket = None
            return False
        start, last_watts, last_outdoor, last_clean = previous
        changed = False
        while start < now:
            slot = floor(start / SLOT) * SLOT
            end = min(now, slot + SLOT)
            if self.bucket is None or self.bucket[0] != slot:
                self.bucket = [slot, 0.0, 0.0, 0.0, True]
            bucket = self.bucket
            seconds = end - start
            bucket[1] += seconds
            bucket[2] += last_watts * seconds / 3_600_000
            bucket[3] += last_outdoor * seconds
            bucket[4] = bucket[4] and last_clean and clean
            if end == slot + SLOT:
                if bucket[1] >= SLOT - 0.01:
                    rows = data.setdefault("buckets", [])
                    rows.append([slot, round(bucket[2], 5), round(bucket[3] / SLOT, 2), bucket[4]])
                    data["buckets"] = [row for row in rows if row[0] >= now - RETENTION]
                    changed = True
                self.bucket = None
            start = end
        return changed

    def observe(
        self, data, now, plan, *, watts, outdoor, automatic, external, preheated, paused, interrupted, local_slot
    ):
        event = data.get("event")
        changed = self.sample(data, now, watts, outdoor, not (event or external))
        if event and interrupted and not event.get("interrupted"):
            event["interrupted"] = True
            changed = True
        if event and now >= event["end"]:
            self.finish(data, event, local_slot)
            data.pop("event")
            event = None
            changed = True
        if not plan:
            return changed
        begins = plan.pause.start if plan.defer else plan.charge.start
        stops = plan.pause.end if plan.defer else plan.charge.end
        if not event and (automatic or external) and begins <= now < stops:
            event = {
                "start": floor(begins / SLOT) * SLOT,
                "peak_start": ceil(plan.pause.start / SLOT) * SLOT,
                "peak_end": floor(plan.pause.end / SLOT) * SLOT,
                "end": ceil((max(plan.pause.end, plan.charge.end) + RECOVERY) / SLOT) * SLOT,
                "plan_start": plan.charge.start,
                "preheated": False,
                "paused": False,
                "interrupted": interrupted,
            }
            data["event"] = event
            changed = True
        if not event or plan.defer or event["plan_start"] != plan.charge.start:
            return changed
        for field, confirmed in (
            ("preheated", preheated or external and now < plan.charge.end),
            ("paused", paused or external and plan.pause.start <= now < plan.pause.end),
        ):
            if confirmed and not event[field]:
                event[field] = True
                changed = True
        return changed

    @staticmethod
    def finish(data, event, local_slot):
        if event.get("interrupted") or not (event["preheated"] and event["paused"]):
            return
        buckets = data.get("buckets", [])
        actual = {row[0]: row for row in buckets if event["start"] <= row[0] < event["end"]}
        reference = {}
        for stamp, energy, temperature, clean in buckets:
            if clean and stamp < event["start"] and stamp >= event["start"] - RETENTION:
                reference.setdefault(local_slot(stamp), []).append((energy, temperature))
        shifted = extra = 0.0
        for stamp in range(event["start"], event["end"], SLOT):
            if stamp not in actual:
                return
            _, energy, temperature, _ = actual[stamp]
            comparable = [
                kwh
                for kwh, baseline_temperature in reference.get(local_slot(stamp), ())
                if abs(temperature - baseline_temperature) <= 2
            ]
            if len(comparable) < 3:
                return
            change = energy - median(comparable)
            extra += change
            if event["peak_start"] <= stamp < event["peak_end"]:
                shifted -= change
        if shifted >= 0.5:
            data.setdefault("results", []).append([event["end"], shifted, extra])
