const PREFIX = "househeating/register_browser";
const PAGE_SIZE = 25;
const hex = (value) => "0x" + value.toString(16).toUpperCase().padStart(4, "0");
const addressLabel = (start, end, bit) => hex(start) + (start !== end ? "–" + hex(end) : bit == null ? "" : ":" + bit);
const rowKey = ([start, end, bit]) => addressLabel(start, end, bit);
const searchText = (value) => value.toLowerCase().normalize("NFD").replace(/\p{Diacritic}/gu, "");
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
    this.entityFilter = "";
    this.openGroups = new Map();
    this.openDetails = new Set();
    this.renderedRows = new Map();
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
          display: block; min-height: 100%; container-type: inline-size;
          background: var(--primary-background-color, #f3f6f8);
          color: var(--primary-text-color, #14232a);
          font: 14px var(--paper-font-body1_-_font-family, system-ui, sans-serif);
          --reg-paper: var(--card-background-color, #fff);
          --reg-line: var(--divider-color, #d9e1e6);
          --reg-muted: var(--secondary-text-color, #536570);
          --reg-accent: var(--primary-color, #006d8a);
          --reg-soft: color-mix(in srgb, var(--reg-accent) 10%, var(--reg-paper));
        }
        * { box-sizing: border-box; }
        header { display: flex; align-items: center; gap: 9px; min-height: 56px; padding: 0 18px;
          border-bottom: 1px solid var(--reg-line); background: var(--app-header-background-color, var(--reg-paper));
          color: var(--app-header-text-color, inherit); }
        h1 { font-size: 20px; font-weight: 680; margin: 0; }
        header a { display: grid; place-items: center; width: 40px; height: 40px; color: inherit;
          font-size: 24px; text-decoration: none; border-radius: 8px; }
        main { max-width: 1180px; margin: auto; padding: 24px clamp(16px, 4cqw, 44px); }
        .toolbar, .grid { background: var(--reg-paper); border: 1px solid var(--reg-line); border-radius: 14px; }
        .toolbar { padding: 16px; }
        .search-line { display: flex; align-items: center; gap: 8px; }
        .search-line label { flex: 1; min-width: 0; }
        .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
        input, select, button, .panel-toggle { min-height: 40px; border: 1px solid var(--reg-line);
          border-radius: 8px; color: inherit; background: var(--reg-paper); padding: 7px 12px; font: inherit; }
        input, select { width: 100%; }
        input { min-height: 44px; }
        button, summary { cursor: pointer; }
        button:hover:not(:disabled), .panel-toggle:hover { border-color: var(--reg-accent); }
        button:disabled { opacity: .55; cursor: default; }
        :where(a, button, input, select, summary):focus-visible { outline: 2px solid var(--reg-accent); outline-offset: 2px; }
        .panel-toggle { min-width: 76px; white-space: nowrap; text-align: center; line-height: 24px; }
        .views { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
        .views button { min-height: 36px; border-radius: 18px; font-size: 13px; }
        .views [aria-pressed="true"], .enable { background: var(--reg-soft); border-color: var(--reg-accent); font-weight: 650; }
        .pane { margin-top: 14px; border-top: 1px solid var(--reg-line); padding-top: 12px; }
        [hidden] { display: none !important; }
        .filter-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(155px, 100%), 1fr)); gap: 10px; }
        .filter-fields label { display: grid; gap: 5px; font-size: 12px; font-weight: 650; }
        .action-fields { display: flex; flex-wrap: wrap; gap: 8px; }
        .bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px 20px;
          margin: 17px 0 10px; color: var(--reg-muted); font-size: 13px; }
        #feedback { background: var(--reg-soft); border-left: 3px solid var(--reg-accent); padding: 9px 12px;
          margin: 0 0 10px; border-radius: 4px; }
        #feedback:empty { display: none; }
        table { width: 100%; table-layout: fixed; border-collapse: collapse; text-align: left; }
        th, td { padding: 11px 16px; border-bottom: 1px solid var(--reg-line); vertical-align: middle; overflow-wrap: anywhere; }
        th { font-size: 12px; color: var(--reg-muted); background: var(--secondary-background-color, #f5f7fa); }
        th:first-child { width: 47%; border-radius: 13px 0 0 0; }
        th:nth-child(2) { width: 24%; }
        th:last-child { border-radius: 0 13px 0 0; }
        tbody tr:last-child td { border-bottom: 0; }
        .title { display: block; font-weight: 650; }
        .register-toggle { text-align: left; background: transparent; padding: 0; min-height: 32px; border: 0; }
        .register-toggle .title::after { content: " ›"; color: var(--reg-accent); }
        .register-toggle[aria-expanded="true"] .title::after { content: " ⌄"; }
        .address, code { font: 12px ui-monospace, monospace; }
        .sub, .address { display: block; margin-top: 3px; color: var(--reg-muted); font-size: 12px; }
        .value { font-weight: 650; }
        .warn { color: var(--error-color, #9c322f); }
        .bit-child td:first-child { padding-inline-start: 32px; }
        .bits { margin-top: 6px; min-height: 29px; padding: 2px 8px; font-size: 12px; }
        .entity-status { display: inline-block; border: 1px solid var(--reg-line); border-radius: 16px;
          padding: 3px 8px; font-size: 12px; font-weight: 650; }
        .entity-status.active { background: var(--reg-soft); }
        .entity-summary + .entity-summary { margin-top: 5px; }
        .detail-row td { background: color-mix(in srgb, var(--reg-muted) 5%, var(--reg-paper)); padding: 14px 16px; }
        .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
          grid-template-areas: "register entity"; gap: 16px; }
        .register-details { grid-area: register; }
        .entity-details { grid-area: entity; }
        .mobile-label { display: none; }
        .detail-row:last-child td { border-radius: 0 0 13px 13px; }
        .detail-grid h2 { font-size: 13px; margin: 0 0 8px; }
        .detail-grid p { margin: 0 0 10px; }
        dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 0 0 10px; font-size: 13px; }
        dt { color: var(--reg-muted); }
        dd { margin: 0; }
        .entity-detail + .entity-detail { margin-top: 12px; }
        .entity-detail code { display: block; margin: 4px 0 8px; color: var(--reg-muted); }
        .entity-detail button + button { margin-inline-start: 6px; }
        footer { display: flex; justify-content: end; align-items: center; gap: 9px; padding: 12px 0; }
        @container (max-width: 620px) {
          main { padding: 12px; }
          header { padding-inline: 9px; }
          .toolbar { padding: 10px; }
          .search-line { flex-wrap: wrap; }
          .search-line label { flex-basis: 100%; }
          .views { margin-top: 8px; }
          table, tbody { display: block; }
          thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
          tbody tr { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 6px 10px; border-bottom: 1px solid var(--reg-line); padding: 10px 12px; }
          tbody tr:last-child, td { border: 0; }
          td { padding: 0; }
          td:first-child { grid-column: 1 / -1; }
          .bit-child { padding-inline-start: 24px; }
          .bit-child td:first-child { padding: 0; }
          .detail-row td { padding: 0; background: transparent; }
          .detail-row { background: color-mix(in srgb, var(--reg-muted) 5%, var(--reg-paper)); }
          .detail-row:last-child { border-radius: 0 0 13px 13px; }
          .detail-grid { grid-template-columns: minmax(0, 1fr); grid-template-areas: "entity" "register"; }
          .mobile-label { display: block; color: var(--reg-muted); font-size: 11px; margin-bottom: 3px; }
        }
      </style>
      <header><a href="/config/integrations/integration/househeating" aria-label="Terug naar de HouseHeating-integratie">←</a><h1>Registerbrowser</h1></header>
      <main>
        <div class="toolbar">
          <div class="search-line">
            <label for="query"><span class="sr-only">Zoeken</span><input id="query" type="search"
              placeholder="Zoek op naam, adres, bit of entiteit-ID"></label>
            <button id="filtersToggle" type="button" class="panel-toggle" aria-expanded="false" aria-controls="filters">Filters</button>
            <button id="actionsToggle" type="button" class="panel-toggle" aria-expanded="false" aria-controls="actions">Acties</button>
          </div>
          <div class="views" role="group" aria-label="Filter op HA-entiteit">
            <button type="button" data-view="">Alle registers</button>
            <button type="button" data-view="linked">Met HA-entiteit</button>
            <button type="button" data-view="disabled" aria-label="Uitgeschakelde entiteiten">Uitgeschakeld</button>
          </div>
          <div id="filters" class="pane" hidden>
            <div class="filter-fields">
              <label for="device">Warmtepomp<select id="device"></select></label>
              <label for="group">Registergroep<select id="group"><option value="">Alle groepen</option></select></label>
              <label for="state">Uitleesstatus<select id="state">
                <option value="">Alle waarden</option><option value="read">Met uitlezing</option>
                <option value="empty">Zonder uitlezing</option><option value="error">Leesfout</option>
              </select></label>
              <label for="entityFilter">HA-entiteit<select id="entityFilter">
                <option value="">Alle registers</option><option value="linked">Met HA-entiteit</option><option value="enabled">Ingeschakeld</option>
                <option value="disabled">Uitgeschakeld</option><option value="none">Geen entiteit</option>
              </select></label>
              <label for="access">Modbus-toegang<select id="access">
                <option value="">Alle toegangstypen</option><option value="R">Alleen lezen</option>
                <option value="RW">Lezen en schrijven</option><option value="W">Alleen schrijven</option>
                <option value="Onbekend">Onbekend</option>
              </select></label>
            </div>
          </div>
          <div id="actions" class="pane action-fields" hidden>
            <button id="refresh" type="button">Ververs weergave</button>
            <button id="batch" type="button">Lees deze pagina</button>
            <button id="readFiltered" type="button">Lees alle resultaten</button>
            <button id="export" type="button">Exporteer JSON</button>
          </div>
        </div>
        <div class="bar"><span id="status" role="status">Registerkaart laden…</span><span id="activeDevice"></span></div>
        <div id="feedback" role="status"></div>
        <div class="grid">
          <table aria-label="Modbus-registers"><thead><tr>
            <th scope="col">Register</th><th scope="col">Waarde</th><th scope="col">HA-entiteit</th>
          </tr></thead><tbody id="results"></tbody></table>
        </div>
        <footer id="pagination"><button id="prev" type="button">Vorige</button><span id="page"></span><button id="next" type="button">Volgende</button></footer>
      </main>`;
    this.ui = Object.fromEntries([...this.shadowRoot.querySelectorAll("[id]")].map((node) => [node.id, node]));
    this.views = [...this.shadowRoot.querySelectorAll("[data-view]")];
    for (const button of this.views) button.onclick = () => this.setEntityFilter(button.dataset.view);
    this.ui.entityFilter.onchange = () => this.setEntityFilter(this.ui.entityFilter.value);
    this.ui.query.value = new URLSearchParams(location.search).get("q") || "";
    for (const key of ["query", "group", "access", "state"]) {
      this.ui[key].addEventListener(key === "query" ? "input" : "change", () => {
        if (key === "query") this.updateLocation();
        this.openGroups.clear();
        this.page = 0;
        this.render();
      });
    }
    for (const key of ["filters", "actions"]) {
      const toggle = this.ui[key + "Toggle"];
      toggle.onclick = () => {
        const pane = this.ui[key];
        pane.hidden = !pane.hidden;
        toggle.setAttribute("aria-expanded", String(!pane.hidden));
      };
    }
    this.ui.device.addEventListener("change", () => {
      this.entry = this.ui.device.value;
      this.snapshot = null;
      this.ui.feedback.textContent = "";
      this.page = 0;
      this.updateLocation();
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

  updateLocation() {
    const url = new URL(location.href);
    for (const [key, value] of [["q", this.ui.query.value.trim()], ["config_entry", this.entry]]) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    history.replaceState(history.state, "", url);
  }

  setEntityFilter(value) {
    this.entityFilter = value;
    this.openGroups.clear();
    this.page = 0;
    this.render();
  }

  async load() {
    if (!this._hass || this.loading || this.loaded) return;
    this.loading = true;
    try {
      const reply = await this._hass.callWS({ type: PREFIX + "/catalog" });
      this.rows = reply.rows;
      this.words = new Map(this.rows.filter(([start, end, bit]) => start === end && bit == null).map((row) => [row[0], row]));
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
    const poll = this.snapshot?.samples?.[address];
    const manual = this.manual.get(this.readKey(address));
    return manual && (!poll || manual.at > poll.at) ? manual : poll;
  }

  entities(address, bit) {
    const key = bit == null ? String(address) : address + ":" + bit;
    return this.snapshot?.entities?.[key] ?? [];
  }

  filtered() {
    const query = searchText(this.ui.query.value.trim());
    const tokens = query.split(/\s+/);
    const addressQuery = /^(?:0x)?([0-9a-f]{1,4})(?::(\d{1,2}))?$/.exec(query);
    const exactAddress = addressQuery && (query.startsWith("0x") || query.includes(":"));
    const group = this.ui.group.value;
    const state = this.ui.state.value;
    const access = this.ui.access.value;
    const entityFilter = this.snapshot?.entities ? this.entityFilter : "";
    return this.rows.filter(([address, end, bit, category, name, mode, , detail]) => {
      if (group && group !== category) return false;
      if (access && mode.split(" · ")[0] !== access) return false;
      if (state === "read" && !this.sample(address)) return false;
      if (state === "empty" && this.sample(address)) return false;
      if (state === "error" && !this.errors.has(this.readKey(address))) return false;
      const entities = end === address ? this.entities(address, bit) : [];
      if (entityFilter === "linked" && !entities.length) return false;
      if (entityFilter === "enabled" && !entities.some((entity) => entity.enabled)) return false;
      if (entityFilter === "disabled" && !entities.some((entity) => !entity.enabled)) return false;
      if (entityFilter === "none" && entities.length) return false;
      if (!query) return true;
      if (exactAddress) {
        const parsed = parseInt(addressQuery[1], 16);
        return address <= parsed && end >= parsed && (addressQuery[2] == null || bit === Number(addressQuery[2]));
      }
      const haystack = searchText([addressLabel(address, end, bit), category, name, detail,
        ...entities.flatMap((entity) => [entity.id, entity.name])].join(" "));
      return tokens.every((token) => haystack.includes(token));
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
    const groups = this.groupRows(this.filtered());
    const selected = all ? groups : groups.slice(this.page * PAGE_SIZE, (this.page + 1) * PAGE_SIZE);
    const addresses = this.readableAddresses(selected);
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
    if (this.ui.status.textContent !== message) this.ui.status.textContent = message;
  }

  groupRows(rows) {
    const groups = new Map();
    for (const row of rows) {
      const [address, end] = row;
      const key = addressLabel(address, end, null);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    return [...groups.values()];
  }

  readableAddresses(groups) {
    return [...new Set(groups.filter((group) => group[0][8] && this.canRead(group[0][0])).map((group) => group[0][0]))];
  }

  render() {
    const hasEntities = !!this.snapshot?.entities;
    this.ui.entityFilter.disabled = !hasEntities;
    this.ui.entityFilter.value = this.entityFilter;
    for (const button of this.views) {
      button.disabled = !hasEntities && !!button.dataset.view;
      button.setAttribute("aria-pressed", String(button.dataset.view === this.entityFilter));
    }
    const advanced = ["group", "access", "state"].filter((key) => this.ui[key].value).length +
      Number(!!this.entityFilter && !this.views.some((button) => button.dataset.view === this.entityFilter));
    this.ui.filtersToggle.textContent = advanced ? "Filters (" + advanced + ")" : "Filters";
    const rows = this.filtered();
    const groups = this.groupRows(rows);
    const pages = Math.max(1, Math.ceil(groups.length / PAGE_SIZE));
    this.page = Math.min(Math.max(0, this.page), pages - 1);
    const visible = groups.slice(this.page * PAGE_SIZE, (this.page + 1) * PAGE_SIZE);
    const result = [];
    for (const group of visible) {
      const word = group[0][2] == null ? group[0] : null;
      const canFold = word && group.length > 1;
      const groupKey = this.entry + "/" + rowKey(group[0]);
      const expanded = this.openGroups.get(groupKey) ?? !!this.ui.query.value.trim();
      const shown = canFold && !expanded ? [word] : group;
      const readOwner = shown.find((row) => this.openDetails.has(this.entry + "/" + rowKey(row)));
      for (const [index, row] of shown.entries()) {
        const key = this.entry + "/" + rowKey(row);
        const open = this.openDetails.has(key);
        const bits = canFold && index === 0 ? { groupKey, expanded, count: group.length - 1 } : null;
        result.push([key, this.renderRow(row, key, open, bits, !!word && index > 0)]);
        if (open) result.push([key + "/details", this.renderDetails(row, row === readOwner)]);
      }
    }
    if (!result.length) {
      const row = element("tr");
      const cell = element("td", this.loaded ? "Geen registers gevonden. Pas de zoekopdracht of filters aan." : "Registerkaart laden…");
      cell.colSpan = 3;
      row.append(cell);
      result.push(["empty", row]);
    }
    this.updateRows(result);
    this.ui.pagination.hidden = pages === 1;
    this.ui.prev.disabled = this.page === 0;
    this.ui.next.disabled = this.page + 1 >= pages;
    this.ui.page.textContent = "Pagina " + (this.page + 1) + " van " + pages;
    this.ui.activeDevice.textContent = this.ui.device.selectedOptions[0]?.text ?? "";
    this.ui.export.disabled = !rows.length;
    const pageReads = this.readableAddresses(visible).length;
    const allReads = this.readableAddresses(groups).length;
    this.ui.batch.disabled = !this.batch && !pageReads;
    this.ui.readFiltered.disabled = !!this.batch || !allReads;
    this.ui.batch.textContent = this.batch ? "Stop na deze uitlezing" : "Lees deze pagina (" + pageReads + ")";
    this.ui.readFiltered.textContent = "Lees alle resultaten (" + allReads + ")";
    const count = rows.length + (rows.length === 1 ? " resultaat" : " resultaten");
    if (this.batch) this.setStatus("Uitlezen: " + this.batch.done + " van " + this.batch.total + " adressen.");
    else if (this.fetchError) this.setStatus("Verbinding met Home Assistant onderbroken. Getoonde waarden kunnen verouderd zijn.");
    else if (this.snapshot?.entry_id) {
      const status = this.snapshot.online ? "Warmtepomp verbonden" : "Warmtepomp offline";
      const shown = groups.length === rows.length ? "" : " · " + groups.length + (groups.length === 1 ? " adres" : " adressen");
      this.setStatus(count + shown + " · " + status + (this.snapshot.has_errors ? " · optionele leesfouten" : ""));
    } else if (this.loaded) this.setStatus("Geen geladen HouseHeating-integratie.");
  }

  updateRows(rows) {
    const body = this.ui.results;
    const active = this.shadowRoot.activeElement;
    const focusKey = body.contains(active) ? active.dataset.focus : null;
    const nextRows = new Map();
    for (const [index, [key, proposed]] of rows.entries()) {
      const previous = this.renderedRows.get(key);
      const node = previous?.isEqualNode(proposed) ? previous : proposed;
      const current = body.children[index];
      if (node !== current) body.insertBefore(node, current ?? null);
      if (previous && previous !== node) previous.remove();
      nextRows.set(key, node);
    }
    for (const [key, row] of this.renderedRows) if (!nextRows.has(key)) row.remove();
    this.renderedRows = nextRows;
    if (focusKey && this.shadowRoot.activeElement !== active) this.focusResult(focusKey);
  }

  focusResult(key) {
    const control = this.ui.results.querySelector('[data-focus="' + CSS.escape(key) + '"]:not(:disabled)');
    const selectedView = this.views.find((button) => button.getAttribute("aria-pressed") === "true" && !button.disabled);
    (control ?? selectedView ?? this.ui.query).focus({ preventScroll: true });
  }

  renderRow(rowData, key, open, bits, child) {
    const [address, end, bit, , name, , , , readable] = rowData;
    const row = element("tr");
    if (child) row.className = "bit-child";
    const register = element("td");
    const toggle = element("button");
    toggle.className = "register-toggle";
    toggle.type = "button";
    toggle.dataset.focus = "details/" + key;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) toggle.setAttribute("aria-controls", "detail-" + key);
    const title = element("span", name);
    title.className = "title";
    const code = element("span", addressLabel(address, end, bit));
    code.className = "address";
    toggle.append(title, code);
    toggle.onclick = () => {
      if (this.openDetails.has(key)) this.openDetails.delete(key);
      else this.openDetails.add(key);
      this.render();
    };
    register.append(toggle);
    if (bits) {
      const groupToggle = element("button", bits.count === 1 ? "1 bit" : bits.count + " bits");
      groupToggle.type = "button";
      groupToggle.className = "bits";
      groupToggle.dataset.focus = "bits/" + key;
      groupToggle.setAttribute("aria-expanded", String(bits.expanded));
      groupToggle.setAttribute("aria-label", (bits.expanded ? "Verberg " : "Toon ") + groupToggle.textContent + " bij " + hex(address));
      groupToggle.onclick = () => {
        this.openGroups.set(bits.groupKey, !bits.expanded);
        this.render();
      };
      register.append(element("br"), groupToggle);
    }
    const current = this.renderValue(rowData);
    const entityCell = element("td");
    this.mobileLabel(entityCell, "HA-entiteit");
    const entities = end === address ? this.entities(address, bit) : [];
    if (!entities.length) {
      const reason = end !== address ? "Adresbereik" : !readable ? "Geen ondersteunde uitlezing" : "Geen HA-entiteit";
      this.sub(entityCell, this.snapshot?.entities ? reason : "HA-status onbekend");
    }
    for (const entity of entities) {
      const summary = element("div");
      summary.className = "entity-summary";
      const status = element("span", entity.enabled ? "Ingeschakeld" : "Uitgeschakeld");
      status.className = "entity-status" + (entity.enabled ? " active" : "");
      summary.append(status);
      if (entity.enabled) {
        const state = this._hass.states?.[entity.id]?.state;
        if (state == null) this.sub(summary, "Wacht op status");
        else if (state === "unavailable") this.sub(summary, "Niet beschikbaar");
        else if (state === "unknown") this.sub(summary, "Status onbekend");
      }
      entityCell.append(summary);
    }
    row.append(register, current, entityCell);
    return row;
  }

  renderValue([address, end, bit, , , access]) {
    const cell = element("td");
    const sample = this.sample(address);
    let value;
    if (end !== address) value = "Adresbereik";
    else if (sample && bit != null) {
      const active = !!(sample.raw & (1 << bit));
      const relay = /^Relaisuitgangsstatus/i.test(this.words.get(address)?.[4] ?? "");
      value = relay ? (active ? "Relais actief" : "Relais inactief") : (active ? "Actief" : "Inactief");
      this.sub(cell, active ? "Bitwaarde 1" : "Bitwaarde 0");
    } else if (sample && address >= 0x1000 && address <= 0x10FF) value = sample.raw ? "Actief" : "Inactief";
    else if (sample?.value != null) value = sample.value + (sample.unit ? " " + sample.unit : "");
    else if (sample?.checked) value = "Ongeldige meetwaarde";
    else if (sample) value = hex(sample.raw);
    else if (/^W\b/.test(access)) value = "Alleen schrijven";
    else value = "Nog niet uitgelezen";
    const label = element("span", value);
    label.className = "value";
    cell.prepend(label);
    this.mobileLabel(cell, "Waarde");
    if (this.errors.has(this.readKey(address))) this.sub(cell, "Leesfout", "warn");
    if (sample && (this.fetchError || !this.snapshot?.online)) this.sub(cell, "Laatste bekende waarde");
    return cell;
  }

  renderDetails([address, end, bit, group, , access, pdf, detail, readable], ownsReadAction) {
    const row = element("tr");
    row.className = "detail-row";
    const cell = element("td");
    cell.colSpan = 3;
    cell.id = "detail-" + this.entry + "/" + addressLabel(address, end, bit);
    const sections = element("div");
    sections.className = "detail-grid";
    const register = element("section");
    register.className = "register-details";
    register.append(element("h2", "Registerdetails"));
    if (detail) register.append(element("p", detail));
    const sample = this.sample(address);
    const word = bit != null ? this.words.get(address) : null;
    const metadata = element("dl");
    for (const [key, value] of [
      ["Registerwoord", word?.[4]],
      ["Registergroep", group],
      ["Handleiding", pdf ? "Pagina " + pdf : null],
      ["Modbus-toegang", access],
      ["Integratie", bit == null && this.writable.has(address) ? "Schrijfondersteuning beschikbaar" : null],
      ["Ruwe waarde", sample ? sample.raw + " · " + hex(sample.raw) : null],
      ["Laatst gelezen", sample ? timeFormat.format(sample.at * 1000) : null],
      ["Uitlezing", sample ? (sample.source === "poll" ? "Periodiek" : "Op aanvraag") : null],
    ]) {
      if (value != null) metadata.append(element("dt", key), element("dd", value));
    }
    register.append(metadata);
    const readKey = this.readKey(address);
    if (readable && ownsReadAction) {
      const button = element("button", this.busy.has(readKey) ? "Uitlezen…" : "Register uitlezen");
      button.type = "button";
      button.dataset.focus = "read/" + readKey;
      button.setAttribute("aria-label", "Register " + hex(address) + " uitlezen");
      button.disabled = !this.canRead(address);
      button.setAttribute("aria-disabled", String(this.busy.has(readKey) || !!this.batch));
      button.onclick = () => { if (!this.batch) this.read(address); };
      register.append(button);
      if (address >= 0x1000 && !(this.snapshot?.protocol >= 130)) this.sub(register, "Protocol ≥ 130 vereist");
    } else if (readable) {
      this.sub(register, "De uitleesknop staat bij het eerste geopende detail voor " + hex(address) + ".");
    }
    if (this.errors.has(readKey)) this.sub(register, this.errors.get(readKey), "warn");
    const ha = element("section");
    ha.className = "entity-details";
    ha.append(element("h2", "Home Assistant-entiteit"));
    const entities = end === address ? this.entities(address, bit) : [];
    if (!entities.length) {
      const reason = end !== address ? "Dit is een adresbereik. Kies een afzonderlijk register." :
        !readable ? "De browser ondersteunt voor deze rij geen uitlezing." : "Geen gekoppelde entiteit.";
      ha.append(element("p", this.snapshot?.entities ? reason : "HA-status onbekend."));
    }
    if (entities.length && address >= 0x1000 && !(this.snapshot?.protocol >= 130)) {
      this.sub(ha, "Voor uitlezen van deze spoel is protocolversie 130 of hoger vereist.");
    }
    for (const entity of entities) ha.append(this.renderEntity(entity));
    sections.append(ha, register);
    cell.append(sections);
    row.append(cell);
    return row;
  }

  renderEntity(entity) {
    const node = element("div");
    node.className = "entity-detail";
    const name = entity.name || entity.id;
    node.append(element("strong", name), element("code", entity.id));
    const label = entity.enabled ? "Entiteit uitschakelen" : "Entiteit inschakelen";
    const pending = this.updatingEntities.has(entity.id);
    const button = element("button", pending ? "Bezig…" : label);
    button.type = "button";
    button.className = entity.enabled ? "" : "enable";
    button.disabled = !!this.fetchError;
    button.setAttribute("aria-disabled", String(pending));
    button.dataset.focus = "entity/" + entity.id;
    button.setAttribute("aria-label", label + ": " + name);
    button.onclick = () => this.setEntityEnabled(entity.id, !entity.enabled, name);
    node.append(button);
    const error = this.entityErrors.get(entity.id);
    if (error) this.sub(node, error, "warn");
    return node;
  }

  async setEntityEnabled(entityId, enabled, entityName) {
    const entry = this.entry;
    if (this.updatingEntities.has(entityId)) return;
    this.updatingEntities.add(entityId);
    this.entityErrors.delete(entityId);
    this.render();
    try {
      await this._hass.callWS({
        type: "config/entity_registry/update", entity_id: entityId, disabled_by: enabled ? null : "user",
      });
      if (this.entry === entry) {
        this.ui.feedback.textContent = entityName + (enabled ? " is ingeschakeld in Home Assistant." : " is uitgeschakeld in Home Assistant.");
      }
      await this.refresh();
    } catch {
      const action = enabled ? "Inschakelen" : "Uitschakelen";
      const error = action + " mislukt. Controleer de entiteit in Home Assistant.";
      this.entityErrors.set(entityId, error);
      if (this.entry === entry) this.ui.feedback.textContent = error;
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

  mobileLabel(parent, text) {
    const label = element("span", text);
    label.className = "mobile-label";
    label.setAttribute("aria-hidden", "true");
    parent.prepend(label);
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

