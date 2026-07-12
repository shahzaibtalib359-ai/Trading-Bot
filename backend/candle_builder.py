from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from backend.models import Candle, Tick


def duration_to_seconds(duration: str) -> int:
    parts = duration.split()
    if not parts:
        return 15
    try:
        amount = int(parts[0])
    except ValueError:
        return 15
    unit = parts[1].lower() if len(parts) > 1 else "seconds"
    return amount * 60 if unit.startswith("minute") else amount


class CandleBuilder:
    """Builds or normalizes recent OHLC candles for strategy analysis."""

    def from_ticks(self, ticks: Iterable[Tick], timeframe_seconds: int, limit: int = 120) -> list[Candle]:
        buckets: dict[int, list[Tick]] = {}
        for tick in ticks:
            timestamp = tick.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            bucket = int(timestamp.timestamp()) // timeframe_seconds * timeframe_seconds
            buckets.setdefault(bucket, []).append(tick)

        candles: list[Candle] = []
        for bucket in sorted(buckets):
            bucket_ticks = sorted(buckets[bucket], key=lambda item: item.timestamp)
            prices = [tick.price for tick in bucket_ticks]
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(bucket, tz=timezone.utc),
                    open=prices[0],
                    high=max(prices),
                    low=min(prices),
                    close=prices[-1],
                    volume=sum(tick.volume for tick in bucket_ticks),
                )
            )
        return candles[-limit:]

    def normalize(self, candles: list[Candle], timeframe_seconds: int, limit: int = 120) -> list[Candle]:
        if not candles:
            return []
        source_interval = self._median_interval(candles)
        if source_interval and source_interval <= timeframe_seconds:
            return self._resample(candles, timeframe_seconds, limit)
        return candles[-limit:]

    def fingerprint(self, candles: list[Candle]) -> str:
        if not candles:
            return "empty"
        last = candles[-1]
        return (
            f"{last.timestamp.isoformat()}|{last.open:.8f}|{last.high:.8f}|"
            f"{last.low:.8f}|{last.close:.8f}|{last.volume:.4f}"
        )

    def _resample(self, candles: list[Candle], timeframe_seconds: int, limit: int) -> list[Candle]:
        buckets: dict[int, list[Candle]] = {}
        for candle in candles:
            timestamp = candle.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            bucket = int(timestamp.timestamp()) // timeframe_seconds * timeframe_seconds
            buckets.setdefault(bucket, []).append(candle)

        output: list[Candle] = []
        for bucket in sorted(buckets):
            rows = sorted(buckets[bucket], key=lambda item: item.timestamp)
            output.append(
                Candle(
                    timestamp=datetime.fromtimestamp(bucket, tz=timezone.utc),
                    open=rows[0].open,
                    high=max(row.high for row in rows),
                    low=min(row.low for row in rows),
                    close=rows[-1].close,
                    volume=sum(row.volume for row in rows),
                )
            )
        return output[-limit:]

    @staticmethod
    def _median_interval(candles: list[Candle]) -> int | None:
        if len(candles) < 3:
            return None
        intervals = [
            int((current.timestamp - previous.timestamp).total_seconds())
            for previous, current in zip(candles, candles[1:])
            if current.timestamp > previous.timestamp
        ]
        if not intervals:
            return None
        intervals.sort()
        return intervals[len(intervals) // 2]
