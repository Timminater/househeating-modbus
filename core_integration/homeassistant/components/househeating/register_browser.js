const PREFIX = "househeating/register_browser";
const PAGE_SIZE = 25;
const hex = (value) => "0x" + value.toString(16).toUpperCase().padStart(4, "0");
const timeFormat = new Intl.DateTimeFormat("nl-NL", { dateStyle: "short", timeStyle: "medium" });

function element(tag, text) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
}

function option(value, label) {
  const node = element("option", label);
  node.value = value;
  return node;
}

class HouseHeatingRegisterBrowser extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.rows = [];
    this.writable = new Set();
    this.entry = new URLSearchParams(window.location.search).get("config_entry") || "";
    this.snapshot = null;
    this.manual = new Map();
    this.errors = new Map();
    this.busy = new Set();
    this.updatingEntities = new Set();
    this.entityErrors = new Map();
    this.page = 0;
  }

  connectedCallback() {
    if (!this.shadowRoot.firstChild) this.build();
    this.load();
    this.timer = setInterval(() => {
      if (!document.hidden && this.loaded) this.refresh();
    }, 10000);
  }

  disconnectedCallback() {
    clearInterval(this.timer);
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this.loaded) this.load();
  }

  build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block; min-height: 100%; box-sizing: border-box;
          background: var(--primary-background-color, #f1f5f6);
          color: var(--primary-text-color, #172c32);
          font: 14px var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        * { box-sizing: border-box; }
        header { display: flex; align-items: center; min-height: 56px; padding: 0 16px; gap: 10px;
          border-bottom: 1px solid var(--divider-color, #d4dfe2); background: var(--app-header-background-color, #123943);
          color: var(--app-header-text-color, #fff); }
        h1 { font-size: 19px; font-weight: 600; margin: 0; }
        header a { display: grid; place-items: center; min-width: 44px; min-height: 44px; color: inherit;
          font-size: 24px; text-decoration: none; border-radius: 6px; }
        header a:focus-visible { outline: 2px solid currentColor; }
        main { max-width: 1540px; margin: auto; padding: 22px; }
        .filters, .grid { background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #d4dfe2);
          border-radius: 12px; }
        .filters { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; padding: 14px; }
        .field { display: grid; gap: 5px; flex: 1 1 145px; min-width: 0; }
        .search { flex: 2 1 230px; }
        label { font-size: 12px; font-weight: 650; }
        input, select, button { min-height: 36px; border: 1px solid var(--divider-color, #c0d0d3);
          border-radius: 7px; color: inherit; background: var(--card-background-color, #fff); padding: 6px 10px; font: inherit; }
        input, select { width: 100%; }
        button { cursor: pointer; white-space: nowrap; }
        button:hover:not(:disabled) { border-color: var(--primary-color, #17646f); }
        button:disabled { opacity: .5; cursor: default; }
        button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--primary-color, #17646f); }
        .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 12px 0; }
        .bar > :first-child { margin-right: auto; color: var(--secondary-text-color, #46636a); }
        .grid { overflow: hidden; }
        .scroll { overflow-x: auto; }
        table { width: 100%; min-width: 910px; border-collapse: collapse; text-align: left; }
        th, td { padding: 10px 12px; border-bottom: 1px solid var(--divider-color, #d4dfe2); vertical-align: top; }
        th { font-size: 12px; background: var(--secondary-background-color, #eaf1f2); }
        tr:last-child td { border-bottom: 0; }
        td:nth-child(2) { min-width: 250px; }
        .address { white-space: nowrap; font: 13px ui-monospace, monospace; }
        .sub { display: block; color: var(--secondary-text-color, #46636a); margin-top: 3px; font-size: 12px; }
        .value { font-weight: 680; white-space: nowrap; }
        .warn { color: var(--error-color, #9c322f); }
        td button { min-height: 30px; padding: 3px 8px; }
        .entities { margin-top: 8px; }
        .entity { overflow-wrap: anywhere; }
        .entity button { margin-top: 4px; }
        .entity + .entity { margin-top: 8px; }
        footer { display:flex; justify-content: end; align-items: center; gap: 9px; padding: 12px 0; }
        @media(max-width: 660px) {
          main { padding: 12px; }
          .filters { gap: 8px; padding: 10px; }
          table, tbody { display: block; min-width: 0; }
          thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
          tr { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px;
            padding: 12px; border-bottom: 1px solid var(--divider-color, #d4dfe2); }
          tr:last-child { border: 0; }
          td, td:nth-child(2) { min-width: 0; padding: 0; border: 0; }
          td:nth-child(-n+2), td:nth-child(6) { grid-column: 1 / -1; }
          td:nth-child(3)::before { content: "Waarde"; }
          td:nth-child(4)::before { content: "Ruw"; }
          td:nth-child(5)::before { content: "Laatst gelezen"; }
          td:nth-child(3)::before, td:nth-child(4)::before, td:nth-child(5)::before {
            display: block; font-size: 12px; font-weight: 400; color: var(--secondary-text-color, #46636a); }
          td:nth-child(7) { grid-column: 2; grid-row: 4; }
        }
      </style>
      <header><a href="/config/integrations/integration/househeating" aria-label="Terug naar de HouseHeating-integratie">←</a><h1>HouseHeating-registers</h1></header>
      <main>
        <div class="filters">
          <div class="field"><label for="device">Warmtepomp</label><select id="device"></select></div>
          <div class="field search"><label for="query">Zoeken</label><input id="query" type="search" placeholder="Naam, 0x001C of 0x001C:4"></div>
          <div class="field"><label for="group">Registergroep</label><select id="group"><option value="">Alle groepen</option></select></div>
          <div class="field"><label for="state">Waarde</label><select id="state">
            <option value="">Alle waarden</option><option value="read">Met uitlezing</option>
            <option value="empty">Zonder uitlezing</option><option value="error">Leesfout</option>
          </select></div>
          <div class="field"><label for="entityFilter">HA-entiteit</label><select id="entityFilter">
            <option value="">Alle registers</option><option value="enabled">Ingeschakeld</option>
            <option value="disabled">Uitgeschakeld</option><option value="none">Geen entiteit</option>
          </select></div>
          <div class="field"><label for="access">Modbus-toegang</label><select id="access">
            <option value="">Alle toegangstypen</option><option value="R">Alleen lezen</option>
            <option value="RW">Lezen en schrijven</option><option value="W">Alleen schrijven</option>
            <option value="Onbekend">Onbekend</option>
          </select></div>
        </div>
        <div class="bar">
          <span id="status" role="status">Registerkaart laden…</span>
          <button id="refresh" type="button">Ververs weergave</button>
          <button id="batch" type="button">Lees deze pagina</button>
          <button id="readFiltered" type="button">Lees alle resultaten</button>
          <button id="export" type="button">Exporteer JSON</button>
        </div>
        <div class="grid"><div class="scroll" tabindex="0" aria-label="Modbus-registertabel">
          <table><thead><tr>
            <th scope="col">Adres / bit</th><th scope="col">Register en HA-entiteiten</th><th scope="col">Waarde</th>
            <th scope="col">Ruw</th><th scope="col">Laatst gelezen</th>
            <th scope="col">Modbus-toegang</th><th scope="col">Uitlezen</th>
          </tr></thead><tbody></tbody></table>
        </div></div>
        <footer><button id="prev" type="button">Vorige</button><span id="page"></span><button id="next" type="button">Volgende</button></footer>
      </main>`;
    this.ui = Object.fromEntries([...this.shadowRoot.querySelectorAll("[id]")].map((node) => [node.id, node]));
    for (const key of ["query", "group", "access", "state", "entityFilter"]) {
      this.ui[key].addEventListener(key === "query" ? "input" : "change", () => {
        this.page = 0;
        this.render();
      });
    }
    this.ui.device.addEventListener("change", () => {
      this.entry = this.ui.device.value;
      this.snapshot = null;
      this.page = 0;
      this.render();
      this.refresh();
    });
    this.ui.prev.onclick = () => { this.page -= 1; this.render(); };
    this.ui.next.onclick = () => { this.page += 1; this.render(); };
    this.ui.refresh.onclick = () => this.loaded ? this.refresh() : this.load();
    this.ui.batch.onclick = () => this.readBatch();
    this.ui.readFiltered.onclick = () => this.readBatch(true);
    this.ui.export.onclick = () => this.exportRows();
    this.render();
  }

  async load() {
    if (!this._hass || this.loading || this.loaded) return;
    this.loading = true;
    try {
      const reply = await this._hass.callWS({ type: PREFIX + "/catalog" });
      this.rows = reply.rows;
      this.writable = new Set(reply.writable);
      this.readable = new Set(this.rows.filter((r) => r[2] == null && r[8]).map((r) => r[0]));
      for (const group of new Set(this.rows.map((r) => r[3]))) this.ui.group.append(option(group, group));
      this.loaded = true;
      await this.refresh();
    } catch {
      this.setStatus("Registerkaart laden mislukt. Probeer de weergave te verversen.");
    } finally {
      this.loading = false;
    }
  }

  async refresh() {
    const request = {};
    this.refreshRequest = request;
    try {
      const message = { type: PREFIX + "/snapshot" };
      if (this.entry) message.entry_id = this.entry;
      const reply = await this._hass.callWS(message);
      if (this.refreshRequest !== request) return;
      const target = reply.entry_id || (reply.devices.length && reply.devices[0].id) || "";
      const existing = [...this.ui.device.options];
      if (existing.length !== reply.devices.length ||
          existing.some((v, i) => v.value !== reply.devices[i].id || v.textContent !== reply.devices[i].name)) {
        this.ui.device.replaceChildren(...reply.devices.map((d) => option(d.id, d.name)));
      }
      this.entry = target;
      this.ui.device.value = target;
      if (target && !reply.entry_id) return this.refresh();
      this.snapshot = reply;
      this.fetchError = false;
      this.render();
    } catch {
      if (this.refreshRequest !== request) return;
      this.fetchError = true;
      this.render();
    }
  }

  readKey(address, entry = this.entry) {
    return entry + ":" + address;
  }

  sample(address) {
    const poll = this.snapshot?.samples[address];
    const manual = this.manual.get(this.readKey(address));
    return manual && (!poll || manual.at > poll.at) ? manual : poll;
  }

  entities(address, bit) {
    const key = bit == null ? String(address) : address + ":" + bit;
    return this.snapshot?.entities?.[key] ?? [];
  }

  filtered() {
    const query = this.ui.query.value.trim().toLowerCase();
    const group = this.ui.group.value;
    const state = this.ui.state.value;
    const access = this.ui.access.value;
    const entityFilter = this.ui.entityFilter.value;
    return this.rows.filter(([address, end, bit, category, name, mode, , detail]) => {
      if (group && group !== category) return false;
      if (access && mode.split(" · ")[0] !== access) return false;
      if (state === "read" && !this.sample(address)) return false;
      if (state === "empty" && this.sample(address)) return false;
      if (state === "error" && !this.errors.has(this.readKey(address))) return false;
      const entities = end === address ? this.entities(address, bit) : [];
      if (entityFilter === "enabled" && !entities.some((entity) => entity.enabled)) return false;
      if (entityFilter === "disabled" && !entities.some((entity) => !entity.enabled)) return false;
      if (entityFilter === "none" && entities.length) return false;
      if (!query) return true;
      const addressQuery = /^0x([0-9a-f]{1,4})(?::(\d{1,2}))?$/.exec(query);
      if (addressQuery) {
        const parsed = parseInt(addressQuery[1], 16);
        return address <= parsed && end >= parsed && (addressQuery[2] == null || bit === Number(addressQuery[2]));
      }
      return [hex(address), hex(end), category, name, detail, ...entities.flatMap((entity) => [entity.id, entity.name])]
        .join(" ").toLowerCase().includes(query);
    });
  }

  canRead(address) {
    return this.snapshot?.entry_id === this.entry && !this.fetchError && this.readable?.has(address) &&
      (address < 0x1000 || this.snapshot?.protocol >= 130);
  }

  async read(address, rerender = true) {
    const entry = this.entry;
    const key = this.readKey(address, entry);
    if (!this.canRead(address) || this.busy.has(key)) return;
    this.busy.add(key);
    this.errors.delete(key);
    if (rerender) this.render();
    try {
      const value = await this._hass.callWS({ type: PREFIX + "/read", entry_id: entry, address });
      this.manual.set(key, value);
    } catch (error) {
      const reasons = {
        unsupported_protocol: "Spoelen vereisen protocol 130 of hoger.",
        not_loaded: "Warmtepomp niet geladen.",
        not_documented: "Geen gedocumenteerde uitlezing voor dit adres.",
        read_failed: "Leesfout of geen antwoord van de warmtepomp.",
      };
      this.errors.set(key, reasons[error?.code] || "Uitlezen mislukt.");
    } finally {
      this.busy.delete(key);
      if (rerender && this.isConnected) this.render();
    }
  }

  async readBatch(all = false) {
    if (this.batch) {
      this.batch.stop = true;
      return;
    }
    const entry = this.entry;
    const filtered = this.filtered();
    const rows = all ? filtered : filtered.slice(this.page * PAGE_SIZE, (this.page + 1) * PAGE_SIZE);
    const addresses = [...new Set(rows.map((r) => r[0]).filter((a) => this.canRead(a)))];
    const batch = { stop: false, done: 0, total: addresses.length };
    this.batch = batch;
    this.render();
    for (const address of addresses) {
      if (batch.stop || this.entry !== entry || !this.isConnected) break;
      await this.read(address, false);
      batch.done += 1;
      if (this.isConnected) this.render();
    }
    this.batch = null;
    if (this.isConnected) this.render();
  }

  setStatus(message) {
    this.ui.status.textContent = message;
  }

  render() {
    this.ui.entityFilter.disabled = !this.snapshot?.entities;
    if (this.ui.entityFilter.disabled) this.ui.entityFilter.value = "";
    const rows = this.filtered();
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    this.page = Math.min(Math.max(0, this.page), pages - 1);
    const visible = rows.slice(this.page * PAGE_SIZE, (this.page + 1) * PAGE_SIZE);
    const body = this.shadowRoot.querySelector("tbody");
    if (!visible.length) {
      const row = element("tr");
      const cell = element("td", this.loaded ? "Geen registers gevonden." : "Registerkaart laden…");
      cell.colSpan = 7;
      row.append(cell);
      body.replaceChildren(row);
    } else {
      body.replaceChildren(...visible.map((r) => this.renderRow(r)));
    }
    this.ui.prev.disabled = this.page === 0;
    this.ui.next.disabled = this.page + 1 >= pages;
    this.ui.page.textContent = (this.page + 1) + " / " + pages;
    this.ui.export.disabled = !rows.length;
    this.ui.batch.disabled = !this.batch && !visible.some((row) => this.canRead(row[0]));
    this.ui.readFiltered.disabled = !!this.batch || !rows.some((row) => this.canRead(row[0]));
    this.ui.batch.textContent = this.batch ? "Stop na deze uitlezing" : "Lees deze pagina";
    if (this.batch) this.setStatus("Uitlezen: " + this.batch.done + " van " + this.batch.total + " adressen.");
    else if (this.fetchError) this.setStatus("Verbinding met Home Assistant onderbroken. Getoonde waarden zijn mogelijk verouderd.");
    else if (this.snapshot?.entry_id) {
      const status = this.snapshot.online ? "Verbonden" : "Warmtepomp offline · waarden van laatste uitlezing";
      this.setStatus(rows.length + " rijen · " + status + (this.snapshot.has_errors ? " · optionele leesfouten" : ""));
    } else if (this.loaded) this.setStatus("Geen geladen HouseHeating-integratie.");
  }

  renderRow([address, end, bit, group, name, access, pdf, detail, readable]) {
    const row = element("tr");
    const sample = this.sample(address);
    const addressText = hex(address) + (end !== address ? "–" + hex(end) : "");
    const addressCell = element("td", addressText);
    addressCell.className = "address";
    if (bit != null) this.sub(addressCell, "Bit " + bit);
    const nameCell = element("td", name);
    this.sub(nameCell, group + " · PDF p. " + pdf);
    if (detail) this.sub(nameCell, detail);
    if (this.snapshot?.entry_id) {
      const entities = end === address ? this.entities(address, bit) : [];
      if (entities.length) {
        const entityList = element("div");
        entityList.className = "entities";
        for (const entity of entities) entityList.append(this.renderEntity(entity));
        nameCell.append(entityList);
      } else if (this.snapshot.entities) this.sub(nameCell, "Geen HA-entiteit");
    }
    const current = element("td");
    if (sample && bit != null) current.textContent = (sample.raw & (1 << bit)) ? "1 · actief" : "0 · inactief";
    else if (sample?.value != null) current.textContent = sample.value + (sample.unit ? " " + sample.unit : "");
    else if (sample?.checked) current.textContent = "Ongeldige meetwaarde";
    else if (sample) current.textContent = "Ruwe waarde";
    else current.textContent = "—";
    current.className = "value";
    const raw = element("td", sample ? sample.raw.toString() : "—");
    if (sample) this.sub(raw, hex(sample.raw));
    const timestamp = element("td", sample ? timeFormat.format(sample.at * 1000) : "—");
    if (sample) this.sub(timestamp, sample.source === "poll" ? "Periodiek" : "Op aanvraag");
    const accessCell = element("td", access);
    if (bit == null && this.writable.has(address)) this.sub(accessCell, "Schrijfondersteuning in integratie");
    const action = element("td");
    const key = this.readKey(address);
    const error = this.errors.get(key);
    if (readable) {
      const button = element("button", this.busy.has(key) ? "Leest…" : "Lees");
      button.type = "button";
      button.setAttribute("aria-label", "Lees register " + hex(address));
      button.disabled = !this.canRead(address) || this.busy.has(key) || !!this.batch;
      button.onclick = async () => {
        await this.read(address);
        const nextButton = [...this.shadowRoot.querySelectorAll("tbody button")].find(
          (item) => item.getAttribute("aria-label") === button.getAttribute("aria-label")
        );
        nextButton?.focus();
      };
      action.append(button);
      if (address >= 0x1000 && !(this.snapshot?.protocol >= 130)) this.sub(action, "Protocol ≥ 130 vereist");
    } else action.textContent = "—";
    if (error) this.sub(action, error, "warn");
    row.append(addressCell, nameCell, current, raw, timestamp, accessCell, action);
    return row;
  }

  renderEntity(entity) {
    const node = element("div");
    node.className = "entity";
    const name = element("div", entity.name || entity.id);
    name.title = entity.id;
    node.append(name);
    if (entity.enabled) {
      const state = this._hass.states?.[entity.id]?.state;
      this.sub(node, state == null ? "Ingeschakeld · wacht op status" :
        state === "unavailable" ? "Ingeschakeld · niet beschikbaar" : "Ingeschakeld");
    } else this.sub(node, "Uitgeschakeld");
    const label = entity.enabled ? "Uitschakelen" : "Inschakelen";
    const pending = this.updatingEntities.has(entity.id);
    const button = element("button", pending ? "Bezig…" : label);
    button.type = "button";
    button.disabled = pending || !!this.fetchError;
    button.dataset.entity = entity.id;
    button.setAttribute("aria-label", label + ": " + (entity.name || entity.id));
    button.onclick = async () => {
      await this.setEntityEnabled(entity.id, !entity.enabled);
      this.shadowRoot.querySelector('button[data-entity="' + CSS.escape(entity.id) + '"]')?.focus();
    };
    node.append(button);
    const error = this.entityErrors.get(entity.id);
    if (error) this.sub(node, error, "warn");
    return node;
  }

  async setEntityEnabled(entityId, enabled) {
    if (this.updatingEntities.has(entityId)) return;
    this.updatingEntities.add(entityId);
    this.entityErrors.delete(entityId);
    this.render();
    try {
      await this._hass.callWS({
        type: "config/entity_registry/update", entity_id: entityId, disabled_by: enabled ? null : "user",
      });
      await this.refresh();
    } catch {
      const action = enabled ? "Inschakelen" : "Uitschakelen";
      this.entityErrors.set(entityId, action + " mislukt. Controleer de entiteit in Home Assistant.");
    } finally {
      this.updatingEntities.delete(entityId);
      if (this.isConnected) this.render();
    }
  }

  sub(parent, label, extraClass = "") {
    const child = element("span", label);
    child.className = "sub " + extraClass;
    parent.append(child);
  }

  exportRows() {
    const rows = this.filtered().map(([address, end, bit, group, name, access, pdf, detail]) => ({
      address: hex(address), last_address: hex(end), bit, group, name, access,
      integration_write_support: bit == null && this.writable.has(address), pdf_page: pdf, detail,
      sample: this.sample(address) ?? null,
      bit_value: bit != null && this.sample(address) ? (this.sample(address).raw >> bit) & 1 : null,
      error: this.errors.get(this.readKey(address)) ?? null,
      entities: end === address ? this.entities(address, bit) : [],
    }));
    const url = URL.createObjectURL(new Blob([JSON.stringify({ device: this.ui.device.selectedOptions[0]?.text, rows }, null, 2)],
      { type: "application/json" }));
    const link = element("a");
    link.href = url;
    link.download = "HouseHeating-registers.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

const revision = /register_browser-([a-f0-9]{16})\.js$/.exec(new URL(import.meta.url).pathname)?.[1];
const componentName = revision ? `househeating-register-browser-${revision}` : "househeating-register-browser";
if (!customElements.get(componentName)) {
  customElements.define(componentName, HouseHeatingRegisterBrowser);
}

