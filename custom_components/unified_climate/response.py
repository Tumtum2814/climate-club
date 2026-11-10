"""Advisory temperature response only; never a control input."""

import statistics

from .control import aggregate


def slope(points):
    """Least-squares Fahrenheit/minute; repeated timestamps add no evidence."""
    if len(points) < 2:
        return None
    times = [p[0] / 60 for p in points]
    center = statistics.mean(times)
    denom = sum((t - center) ** 2 for t in times)
    if not denom:
        return None
    mean = statistics.mean(p[1] for p in points)
    return (
        sum((t - center) * (p[1] - mean) for t, p in zip(times, points, strict=True))
        / denom
    )


class ResponseMonitor:
    def __init__(self, config):
        self.config = config
        self.sensors = tuple(
            dict.fromkeys(config["response_sensors"] or config["sensors"])
        )
        self.samples = {e: [] for e in self.sensors}
        self.identities = {}
        self.state = "inconclusive" if config["response_enabled"] else "disabled"
        self.reason = (
            "No issued cooling command"
            if config["response_enabled"]
            else "Monitoring disabled"
        )
        self.direction = None
        self.started = None
        self.baseline = {}
        self.baseline_slope = None
        self.post_slope = None
        self.post_counts = {}
        self.units = {}
        self.last_command = None
        self.now = 0

    def invalidate(self, reason):
        if self.state == "disabled":
            return
        self.state = "inconclusive"
        self.reason = reason
        self.samples = {e: [] for e in self.sensors}
        self.baseline = {}
        self.baseline_slope = self.post_slope = None
        self.post_counts = {}

    def reading(self, entity, value, unit, identity, now):
        if self.state == "disabled" or entity not in self.samples:
            return
        if self.identities.get(entity) == identity:
            return
        self.identities[entity] = identity
        number = aggregate([(value, unit, 0)])
        if number is None:
            self.invalidate("Invalid or missing feedback reading")
            return
        if entity in self.units and self.units[entity] != unit:
            self.invalidate("Feedback units changed; new baseline required")
        self.units[entity] = unit
        points = self.samples[entity]
        if points and now <= points[-1][0]:
            return
        if points and now - points[-1][0] > self.config["stale_after"]:
            self.invalidate("Stale feedback gap; new baseline required")
            points = self.samples[entity]
        points.append((now, number))
        retention = max(
            self.config["response_baseline_window"],
            self.config["response_start_window"] + self.config["response_start_grace"],
            self.config["response_stop_window"] + self.config["response_stop_settling"],
        )
        cutoff = now - retention
        self.samples[entity] = [p for p in points if p[0] >= cutoff][-10000:]

    def command(self, direction, now, delivered=True):
        if self.state == "disabled":
            return
        if not delivered:
            self.last_command = direction
            self.invalidate(
                "Cooling service error: delivery ambiguous, no inferred confirmation"
            )
            return
        if self.last_command == direction:
            return  # Native retries and additional zone ACs do not restart a window.
        self.last_command = direction
        self.direction = direction
        self.started = now
        self.baseline = {
            e: [
                p
                for p in points
                if now - self.config["response_baseline_window"] <= p[0] <= now
            ]
            for e, points in self.samples.items()
        }
        self.post_slope = None
        self.baseline_slope = None
        self.post_counts = {}
        self.state = "observing_" + direction
        self.reason = "Awaiting post-grace fresh reports; inference only"

    @property
    def diagnostics(self):
        return {
            "state": self.state,
            "reason": self.reason,
            "inference_only": True,
            "direction": self.direction,
            "command_at_monotonic": self.started,
            "sensors": list(self.sensors),
            "freshness_seconds": {
                e: max(0, self.now - p[-1][0]) if p else None
                for e, p in self.samples.items()
            },
            "baseline_counts": {e: len(p) for e, p in self.baseline.items()},
            "post_counts": dict(self.post_counts),
            "baseline_slope_f_per_min": self.baseline_slope,
            "post_slope_f_per_min": self.post_slope,
            "windows_seconds": {
                k: v
                for k, v in self.config.items()
                if k.startswith("response_")
                and k.endswith(("window", "grace", "settling"))
            },
            "min_samples_per_sensor": self.config["response_min_samples"],
            "threshold_f_per_min": self.config["response_threshold"],
        }

    def advance(self, now):
        self.now = now
        if self.state == "disabled":
            return
        stale = any(
            p and now - p[-1][0] > self.config["stale_after"]
            for p in self.samples.values()
        )
        missing_during_window = self.state.startswith("observing_") and any(
            not p for p in self.samples.values()
        )
        if stale or missing_during_window:
            self.invalidate("Missing or stale feedback; new baseline required")
            return
        if not self.state.startswith("observing_"):
            return
        grace = self.config[
            "response_start_grace"
            if self.direction == "start"
            else "response_stop_settling"
        ]
        end = self.started + grace + self.config[f"response_{self.direction}_window"]
        post = {
            e: [p for p in points if self.started + grace < p[0] <= end]
            for e, points in self.samples.items()
        }
        self.post_counts = {e: len(p) for e, p in post.items()}
        minimum = self.config["response_min_samples"]
        reducer = (
            statistics.mean
            if self.config["aggregation"] == "mean"
            else statistics.median
        )
        if self.baseline and all(
            len(p) >= minimum and slope(p) is not None for p in self.baseline.values()
        ):
            self.baseline_slope = reducer(slope(p) for p in self.baseline.values())
        if now < end:
            return
        if set(self.baseline) != set(self.sensors) or any(
            len(p) < minimum or slope(p) is None
            for p in [*self.baseline.values(), *post.values()]
        ):
            self.state = "inconclusive"
            self.reason = "Insufficient baseline or fresh post-grace reports"
            return
        reducer = (
            statistics.mean
            if self.config["aggregation"] == "mean"
            else statistics.median
        )
        self.baseline_slope = reducer(slope(p) for p in self.baseline.values())
        self.post_slope = reducer(slope(p) for p in post.values())
        threshold = self.config["response_threshold"]
        if self.direction == "start":
            consistent = self.baseline_slope - self.post_slope >= threshold
            self.state = "cooling_likely" if consistent else "no_start_response"
        else:
            consistent = (
                self.post_slope >= -threshold
                or self.post_slope - self.baseline_slope >= threshold
            )
            self.state = "stopped_likely" if consistent else "continued_cooling"
        self.reason = "Temperature response inference, not physical confirmation; continued cooling may be natural settling"
