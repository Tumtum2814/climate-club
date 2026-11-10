// No external dependencies. Every plotted temperature is °F.
const time = (row) => Date.parse(row.last_updated || row.last_changed);
const temperature = (row) => {
  const n = Number(row.state),
    unit = row.attributes?.unit_of_measurement;
  if (
    !Number.isFinite(n) ||
    String(row.state).trim() === "" ||
    !["°C", "°F"].includes(unit)
  )
    return null;
  return unit === "°C" ? n * 1.8 + 32 : n;
};
export function segments(indoor, operation, maxGap = 1800000, inferred = []) {
  const points = [...indoor].sort((a, b) => time(a) - time(b));
  const actions = [...operation].sort((a, b) => time(a) - time(b));
  const evidence = [...inferred].sort((a, b) => time(a) - time(b));
  const result = [];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      start = time(a),
      end = time(b),
      v0 = temperature(a),
      v1 = temperature(b);
    if (
      v0 === null ||
      v1 === null ||
      !Number.isFinite(start + end) ||
      end <= start ||
      end - start > maxGap
    )
      continue;
    const cuts = [
      ...new Set([
        start,
        ...[...actions, ...evidence]
          .map(time)
          .filter((t) => t > start && t < end),
        end,
      ]),
    ].sort((a, b) => a - b);
    for (let j = 1; j < cuts.length; j++) {
      const left = cuts[j - 1],
        right = cuts[j];
      const action = actions.filter((r) => time(r) <= left).at(-1)?.state;
      const inference = evidence.filter((r) => time(r) <= left).at(-1)?.state;
      const value = (t) => v0 + ((v1 - v0) * (t - start)) / (end - start);
      result.push({
        action: ["heating", "cooling", "idle"].includes(action)
          ? action
          : inference === "cooling_likely"
            ? "inferred_cooling"
            : inference === "stopped_likely"
              ? "inferred_idle"
              : "unknown",
        points: [
          [left, value(left)],
          [right, value(right)],
        ],
      });
    }
  }
  return result;
}

export class UnifiedClimateCard extends (globalThis.HTMLElement || class {}) {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.history = {};
    this.lastLoad = 0;
    this.loading = false;
    this.error = "";
  }
  setConfig(config) {
    if (!/^climate\.[a-z0-9_]+$/.test(config.entity || ""))
      throw new Error("entity must be a climate entity");
    this.config = {
      ...config,
      hours: Math.min(72, Math.max(1, Number(config.hours) || 24)),
    };
    this.lastLoad = 0;
    if (this._hass) {
      this.render();
      void this.refresh();
    }
  }
  set hass(hass) {
    this._hass = hass;
    if (this.config) {
      if (!this.shadowRoot.activeElement) this.render();
      void this.refresh();
    }
  }
  connectedCallback() {
    if (this.config && this._hass) {
      this.render();
      void this.refresh();
    }
    this.timer = setInterval(() => void this.refresh(), 60000);
  }
  disconnectedCallback() {
    clearInterval(this.timer);
  }
  getCardSize() {
    return 6;
  }
  async refresh(force = false) {
    if (
      !this._hass ||
      !this.config ||
      this.loading ||
      (!force && Date.now() - this.lastLoad < 60000)
    )
      return;
    const state = this._hass.states[this.config.entity];
    const sensors = {
      ...state?.attributes?.history_sensors,
      ...this.config.sensors,
    };
    const ids = [
      sensors.indoor,
      sensors.outdoor,
      sensors.operation,
      sensors.inferred_operation,
    ].filter(Boolean);
    if (!sensors.indoor || !sensors.operation) {
      this.error =
        "History sensors not found. Configure sensors.indoor / outdoor / operation.";
      this.render();
      return;
    }
    this.loading = true;
    this.lastLoad = Date.now();
    this.end = Date.now();
    this.start = this.end - this.config.hours * 3600000;
    try {
      const url = `history/period/${new Date(this.start).toISOString()}?filter_entity_id=${encodeURIComponent(ids.join(","))}&end_time=${encodeURIComponent(new Date(this.end).toISOString())}`;
      const response = await this._hass.callApi("GET", url);
      this.history = {};
      for (const rows of response)
        if (rows.length) this.history[rows[0].entity_id] = rows;
      this.sensors = sensors;
      this.error = "";
    } catch (error) {
      this.error = `History unavailable: ${error.message || error}`;
      this.history = {};
    } finally {
      this.loading = false;
      this.render();
    }
  }
  async service(name, data) {
    try {
      await this._hass.callService("climate", name, {
        entity_id: this.config.entity,
        ...data,
      });
      this.error = "";
    } catch (error) {
      this.error = `Control failed: ${error.message || error}`;
    }
    this.render();
  }
  render() {
    if (!this.config || !this._hass) return;
    const state = this._hass.states[this.config.entity],
      attrs = state?.attributes || {};
    const escape = (value) =>
      String(value ?? "").replace(
        /[&<>"']/g,
        (c) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[c],
      );
    const fahrenheit = (v) =>
      Number.isFinite(Number(v)) && v != null
        ? attrs.temperature_unit === "°C"
          ? Number(v) * 1.8 + 32
          : Number(v)
        : null;
    const low = fahrenheit(attrs.target_temp_low ?? attrs.temperature),
      high = fahrenheit(attrs.target_temp_high ?? attrs.temperature);
    const current = fahrenheit(attrs.current_temperature);
    const indoor = this.history[this.sensors?.indoor] || [],
      outside = this.history[this.sensors?.outdoor] || [],
      actions = this.history[this.sensors?.operation] || [];
    const maxGap = (Number(this.config.max_gap_minutes) || 30) * 60000;
    const inferred = this.history[this.sensors?.inferred_operation] || [];
    const lines = segments(indoor, actions, maxGap, inferred),
      outLines = segments(outside, [], maxGap);
    const values = [...lines, ...outLines].flatMap((l) =>
      l.points.map((p) => p[1]),
    );
    const min = values.length ? Math.floor(Math.min(...values) - 1) : 50,
      max = values.length ? Math.ceil(Math.max(...values) + 1) : 80;
    const x = (t) => 52 + ((t - this.start) / (this.end - this.start)) * 580,
      y = (v) => 180 - ((v - min) / (max - min)) * 150;
    const path = (l) =>
      l.points
        .map(
          (p, i) =>
            `${i ? "L" : "M"}${x(p[0]).toFixed(2)},${y(p[1]).toFixed(2)}`,
        )
        .join(" ");
    const colors = {
      heating: "#ef5555",
      cooling: "#438bea",
      idle: "#8993a4",
      inferred_cooling: "#438bea",
      inferred_idle: "#8993a4",
      unknown: "#a995b7",
    };
    const paths =
      lines
        .map(
          (l) =>
            `<path data-action="${l.action}" d="${path(l)}" stroke="${colors[l.action]}" ${l.action === "unknown" || l.action.startsWith("inferred_") ? 'stroke-dasharray="3 3"' : ""}/>`,
        )
        .join("") +
      outLines
        .map(
          (l) =>
            `<path data-outdoor d="${path(l)}" stroke="#d99b32" stroke-dasharray="6 3"/>`,
        )
        .join("");
    const ticks = [min, (min + max) / 2, max]
      .map(
        (v) =>
          `<text x="45" y="${y(v) + 4}" text-anchor="end">${v.toFixed(1)}°</text><line x1="52" x2="632" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity=".1"/>`,
      )
      .join("");
    const labels = this.start
      ? `<text x="52" y="207">${escape(new Date(this.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</text><text x="632" y="207" text-anchor="end">${escape(new Date(this.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</text>`
      : "";
    this.shadowRoot.innerHTML = `<style>:host{display:block}ha-card{display:block;padding:20px;color:var(--primary-text-color,#e7ecf5);background:var(--ha-card-background,#17202d);border-radius:14px;font:14px system-ui}header{display:flex;align-items:center;justify-content:space-between}h2{font-size:19px;margin:0 0 6px}.temp{font-size:32px;font-weight:600}.sub{opacity:.75}svg{width:100%;height:auto;margin-top:12px}svg path{fill:none;stroke-width:2.5}svg text{fill:currentColor;font:11px system-ui}.controls{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px;align-items:end}label{display:grid;gap:5px}input{width:75px}input,select,button{font:inherit;background:var(--secondary-background-color,#243246);color:inherit;border:1px solid #697487;border-radius:6px;padding:7px}button{cursor:pointer}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px}.error{color:#efa9a9}.note{font-size:11px;opacity:.7;margin-top:12px}</style><ha-card><header><div><h2>${escape(this.config.title || attrs.friendly_name || this.config.entity)}</h2><div class="sub">${escape(state?.state || "unavailable")} · requested ${escape(attrs.requested_action || "off")}</div></div><span class="temp">${current === null ? "—" : current.toFixed(1)}°F</span></header><div class="controls"><label>Mode<select aria-label="HVAC mode">${(attrs.hvac_modes || ["off"]).map((mode) => `<option value="${escape(mode)}" ${mode === state?.state ? "selected" : ""}>${escape(mode)}</option>`).join("")}</select></label><label>Heat °F<input data-low aria-label="Heat target Fahrenheit" type="number" min="50" max="85" step="0.1" value="${low ?? 68}"></label><label>Cool °F<input data-high aria-label="Cool target Fahrenheit" type="number" min="50" max="85" step="0.1" value="${high ?? 75}"></label><button data-apply>Set targets</button><label>History<select data-hours aria-label="History range">${[1, 6, 12, 24, 48, 72].map((h) => `<option value="${h}" ${h === this.config.hours ? "selected" : ""}>${h}h</option>`).join("")}</select></label></div><svg viewBox="0 0 650 220" role="img" aria-label="Indoor temperature Fahrenheit colored by reported HVAC action, outdoor dashed gold">${ticks}${paths}${labels}</svg>${!paths ? "<p>No recorded temperature intervals in this range.</p>" : ""}<div class="legend"><span style="color:#ef5555">● Heating</span><span style="color:#438bea">● Cooling</span><span style="color:#8993a4">● Idle</span><span style="color:#438bea">┄ Inferred cooling</span><span style="color:#8993a4">┄ Inferred stopped</span><span style="color:#a995b7">┄ Monitoring / unknown</span><span style="color:#d99b32">┄ Outdoors</span></div>${this.error ? `<p class="error" role="alert">${escape(this.error)}</p>` : ""}<div class="note">Solid colors use trusted reported hvac_action. Dashed blue/gray are temperature-response inference, not physical confirmation; purple is monitoring/uncertain. Requested demand is not inference. IR commands do not verify compressor operation. Gaps are not interpolated across missing data.</div></ha-card>`;
    this.shadowRoot.querySelector("select").onchange = (event) =>
      void this.service("set_hvac_mode", { hvac_mode: event.target.value });
    this.shadowRoot.querySelector("[data-hours]").onchange = (event) => {
      this.config.hours = Number(event.target.value);
      void this.refresh(true);
    };
    this.shadowRoot.querySelector("[data-apply]").onclick = () => {
      const l = Number(this.shadowRoot.querySelector("[data-low]").value),
        h = Number(this.shadowRoot.querySelector("[data-high]").value);
      if (!Number.isFinite(l + h) || l < 50 || h > 85 || l >= h) {
        this.error = "Enter valid separated heat/cool targets, 50–85°F";
        this.render();
        return;
      }
      const convert = (v) =>
        attrs.temperature_unit === "°C" ? (v - 32) / 1.8 : v;
      const data = attrs.hvac_modes?.includes("heat_cool")
        ? { target_temp_low: convert(l), target_temp_high: convert(h) }
        : { temperature: convert(state?.state === "cool" ? h : l) };
      void this.service("set_temperature", data);
    };
  }
}
if (globalThis.customElements && !customElements.get("unified-climate-card"))
  customElements.define("unified-climate-card", UnifiedClimateCard);
