import test from "node:test";
import assert from "node:assert/strict";
import { segments } from "../custom_components/unified_climate/frontend/unified-climate-card.js";
const row = (seconds, state, unit = "°F") => ({
  last_changed: new Date(seconds * 1000).toISOString(),
  state: String(state),
  attributes: { unit_of_measurement: unit },
});
test("splits indoor line at observed heating/cooling boundaries and converts C to F", () => {
  const lines = segments(
    [row(0, 20, "°C"), row(100, 22, "°C")],
    [row(0, "heating"), row(50, "cooling")],
  );
  assert.equal(lines.length, 2);
  assert.equal(lines[0].action, "heating");
  assert.equal(lines[1].action, "cooling");
  assert.deepEqual(lines[0].points, [
    [0, 68],
    [50000, 69.8],
  ]);
});
test("invalid temperatures and long sample gaps are not connected; unknown is not idle", () => {
  assert.equal(
    segments(
      [row(0, 68), row(10, "unavailable"), row(20, 70)],
      [row(0, "idle")],
    ).length,
    0,
  );
  assert.equal(
    segments([row(0, 68), row(3600, 70)], [row(0, "idle")]).length,
    0,
  );
  assert.equal(segments([row(0, 68), row(10, 70)], [])[0].action, "unknown");
});
