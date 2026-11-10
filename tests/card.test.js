import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>", {
  url: "http://localhost",
});
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.customElements = dom.window.customElements;
globalThis.document = dom.window.document;
await import("../custom_components/unified_climate/frontend/unified-climate-card.js");
test("card fetches optional inferred history through authenticated API and renders distinct dashed evidence", async () => {
  const card = document.createElement("unified-climate-card");
  card.setConfig({ entity: "climate.zone" });
  const start = Date.now() - 300000;
  const rows = (id, states) =>
    states.map(([offset, state]) => ({
      entity_id: id,
      last_changed: new Date(start + offset).toISOString(),
      state: String(state),
      attributes: { unit_of_measurement: "°F" },
    }));
  let requested;
  card.hass = {
    states: {
      "climate.zone": {
        state: "cool",
        attributes: {
          history_sensors: {
            indoor: "sensor.indoor",
            operation: "sensor.op",
            inferred_operation: "sensor.inferred",
          },
        },
      },
    },
    callApi: async (method, url) => {
      requested = [method, url];
      return [
        rows("sensor.indoor", [
          [0, 75],
          [240000, 74],
        ]),
        rows("sensor.op", [[0, "unknown"]]),
        rows("sensor.inferred", [
          [0, "cooling_likely"],
          [60000, "stopped_likely"],
          [120000, "observing_start"],
        ]),
      ];
    },
    callService: async () => {
      throw new Error("monitor must not control");
    },
  };
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(requested[0], "GET");
  assert.match(decodeURIComponent(requested[1]), /sensor.inferred/);
  for (const action of ["inferred_cooling", "inferred_idle", "unknown"]) {
    assert.ok(
      card.shadowRoot
        .querySelector(`[data-action="${action}"]`)
        .hasAttribute("stroke-dasharray"),
    );
  }
  assert.match(card.shadowRoot.textContent, /Inferred cooling/);
  assert.match(card.shadowRoot.textContent, /Inferred stopped/);
});

test("card loads authenticated native history, plots colors/outside and controls only on user input", async () => {
  const requests = [],
    services = [];
  const start = Date.now() - 300000;
  const row = (offset, state, unit = "°F") => ({
    last_changed: new Date(start + offset).toISOString(),
    state: String(state),
    attributes: { unit_of_measurement: unit },
  });
  const climate = {
    state: "off",
    attributes: {
      friendly_name: "Fixture zone",
      temperature_unit: "°F",
      target_temp_low: 68,
      target_temp_high: 75,
      hvac_modes: ["off", "heat", "cool", "heat_cool"],
      history_sensors: {
        indoor: "sensor.indoor",
        outdoor: "sensor.outdoor",
        operation: "sensor.op",
      },
    },
  };
  const card = document.createElement("unified-climate-card");
  card.setConfig({ entity: "climate.zone", hours: 1 });
  card.hass = {
    states: { "climate.zone": climate },
    callApi: async (method, url) => {
      requests.push([method, url]);
      return [
        [row(0, 68), row(120000, 70), row(240000, 71)].map((r) => ({
          ...r,
          entity_id: "sensor.indoor",
        })),
        [row(0, 40), row(240000, 41)].map((r) => ({
          ...r,
          entity_id: "sensor.outdoor",
        })),
        [row(0, "heating"), row(60000, "cooling"), row(180000, "idle")].map(
          (r) => ({ ...r, entity_id: "sensor.op" }),
        ),
      ];
    },
    callService: async (...args) => services.push(args),
  };
  document.body.append(card);
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(requests.length, 1);
  assert.match(requests[0][1], /^history\/period\//);
  assert.match(requests[0][1], /filter_entity_id=/);
  assert.equal(services.length, 0);
  const root = card.shadowRoot;
  assert.ok(root.querySelector('[data-action="heating"]'));
  assert.ok(root.querySelector('[data-action="cooling"]'));
  assert.ok(root.querySelector('[data-action="idle"]'));
  assert.ok(root.querySelector("[data-outdoor]"));
  root.querySelector("select").value = "heat";
  root.querySelector("select").dispatchEvent(new dom.window.Event("change"));
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(services[0], [
    "climate",
    "set_hvac_mode",
    { entity_id: "climate.zone", hvac_mode: "heat" },
  ]);
  card.remove();
});
