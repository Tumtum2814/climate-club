import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>");
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.customElements = dom.window.customElements;
globalThis.document = dom.window.document;
await import("../custom_components/unified_climate/frontend/unified-climate-card.js");

async function setup(mode, modes, metric = false) {
  const calls = [];
  const card = document.createElement("unified-climate-card");
  card.setConfig({ entity: "climate.zone" });
  card.hass = {
    states: {
      "climate.zone": {
        state: mode,
        attributes: {
          hvac_modes: modes,
          temperature_unit: metric ? "°C" : "°F",
          target_temp_low: metric ? 20 : 68,
          target_temp_high: metric ? 25 : 77,
          min_band_f: 4,
        },
      },
    },
    callApi: async () => [],
    callService: async (...args) => calls.push(args),
  };
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { card, calls };
}

test("explicit heat/cool band is validated locally using the configured gap", async () => {
  const { card, calls } = await setup("heat_cool", [
    "off",
    "heat",
    "cool",
    "heat_cool",
  ]);
  card.shadowRoot.querySelector("[data-low]").value = 72;
  card.shadowRoot.querySelector("[data-high]").value = 74;
  card.shadowRoot.querySelector("[data-apply]").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.length, 0);
  assert.match(card.shadowRoot.textContent, /at least 4°F/);
  card.shadowRoot.querySelector("[data-low]").value = 70;
  card.shadowRoot.querySelector("[data-high]").value = 74;
  card.shadowRoot.querySelector("[data-apply]").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls[0], [
    "climate",
    "set_temperature",
    {
      entity_id: "climate.zone",
      target_temp_low: 70,
      target_temp_high: 74,
    },
  ]);
});

for (const [mode, modes, field, target] of [
  ["heat", ["off", "heat", "cool", "heat_cool"], "low", 74],
  ["cool", ["off", "heat", "cool", "heat_cool"], "high", 66],
  ["off", ["off", "cool"], "high", 60],
  ["off", ["off", "heat"], "low", 85],
]) {
  test(`${mode}/${modes.join(",")} submits only its usable target`, async () => {
    const { card, calls } = await setup(mode, modes, true);
    assert.equal(card.shadowRoot.querySelectorAll("input").length, 1);
    card.shadowRoot.querySelector(`[data-${field}]`).value = target;
    card.shadowRoot.querySelector("[data-apply]").click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls[0], [
      "climate",
      "set_temperature",
      {
        entity_id: "climate.zone",
        temperature: (target - 32) / 1.8,
      },
    ]);
  });
}
