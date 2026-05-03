let _toastTimer = null;
let _jumpTimer = null;
let _lastJumpKey = "";
let _restoringRamaState = false;
const _ramaPotenciasCache = {};
const _ramaPotenciasCacheMs = 45000;
const _ramaInventarioCargado = {};
const _ramaInventarioCargando = {};
const _RAMA_STATE_KEY = "ramaDashboardStateV1";
const _ramaStateStore = window.createNocPageStateStore
  ? window.createNocPageStateStore(_RAMA_STATE_KEY, { debounceMs: 120 })
  : null;

/** Columnas tabla CTO: OUT…Estado (sin SN ni botón por fila). */
const RAMA_COL_TX = 7;
const RAMA_COL_RX = 8;
const RAMA_COL_EST = 9;

function _ramaFatSkipPotencias(tr) {
  const st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
  return st === "FREE" || st === "RESERVED";
}

function _findTrByAidInCtoBody(ctoBody, aid) {
  const s = String(aid ?? "");
  if (!s || !ctoBody) return null;
  for (const tr of ctoBody.querySelectorAll("tr[data-aid]")) {
    if (String(tr.getAttribute("data-aid") || "") === s) return tr;
  }
  return null;
}

function _ctoBodyTieneFilasPendientesPotencias(ctoBody) {
  if (!ctoBody) return false;
  for (const tr of ctoBody.querySelectorAll("tr[data-aid]")) {
    if (_ramaFatSkipPotencias(tr)) continue;
    const tx = tr.children[RAMA_COL_TX];
    if (tx && tx.classList.contains("olt-txrx-cell--loading")) return true;
  }
  return false;
}

function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 1600);
}

function copyTextToClipboard(text) {
  const done = () => toast("Copiado al portapapeles (pegá en Excel con Ctrl+V)");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).then(done).catch(fallback);
  }
  fallback();
  function fallback() {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (e) {
      toast("No se pudo copiar");
    }
    document.body.removeChild(ta);
  }
}

function descargarCsvRama(filename, lines, delimiter) {
  const sep = delimiter || ",";
  const csv = lines
    .map((line) =>
      String(line)
        .split("\t")
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(sep)
    )
    .join("\r\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "rama_cto_seleccionadas.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function _rowsCtosSeleccionados() {
  const selected = Array.from(document.querySelectorAll(".cto-select:checked"));
  if (selected.length === 0) {
    return { error: "Seleccioná al menos una CTO", lines: [], count: 0 };
  }
  const lines = [];
  lines.push(
    ["Sitio_principal", "RAMA", "CTO", "OUT", "AID", "Operador", "SITIO", "ONT", "STATUS", "TX", "RX", "Estado"].join(
      "\t"
    )
  );
  let n = 0;
  selected.forEach((cb) => {
    const ctoNode = cb.closest("[data-cto-node]");
    if (!ctoNode) return;
    const body = ctoNode.nextElementSibling;
    if (!body) return;
    const card = ctoNode.closest("[data-rama-card]");
    if (!card || card.style.display === "none") return;
    const pb = ctoNode.closest(".principal-block");
    if (!pb || pb.style.display === "none") return;
    const principal = (pb.getAttribute("data-principal-name") || "").trim();
    const rama = (card.getAttribute("data-rama") || "").trim();
    const cto = (ctoNode.getAttribute("data-cto") || "").trim();
    body.querySelectorAll("tr[data-aid]").forEach((tr) => {
      if (getComputedStyle(tr).display === "none") return;
      const cells = [...tr.querySelectorAll("td")];
      lines.push([
        principal,
        rama,
        cto,
        (cells[0]?.innerText || "").trim(),
        (cells[1]?.innerText || "").trim(),
        (cells[2]?.innerText || "").trim(),
        (cells[3]?.innerText || "").trim(),
        (cells[4]?.innerText || "").trim(),
        (cells[5]?.innerText || "").trim(),
        (cells[6]?.innerText || "").trim(),
        (cells[7]?.innerText || "").trim(),
        (cells[8]?.innerText || "").trim(),
        (cells[9]?.innerText || "").trim(),
      ].join("\t"));
      n++;
    });
  });
  if (n === 0) {
    return { error: "No hay filas para exportar con esa selección", lines: [], count: 0 };
  }
  return { error: null, lines, count: n };
}

function copiarCtosSeleccionadas() {
  const res = _rowsCtosSeleccionados();
  if (res.error) {
    toast(res.error);
    return;
  }
  copyTextToClipboard(res.lines.join("\n"));
}

function exportarCtosSeleccionadasCsv() {
  const res = _rowsCtosSeleccionados();
  if (res.error) {
    toast(res.error);
    return;
  }
  descargarCsvRama("rama_cto_seleccionadas.csv", res.lines, ",");
  toast("CSV exportado");
}

function limpiarBusquedaRama() {
  const el = document.getElementById("q");
  if (!el) return;
  el.value = "";
  if (typeof aplicarFiltro === "function") aplicarFiltro();
  el.focus();
}

function colapsarTodoYLimpiarRama() {
  expandAll(false);
  limpiarBusquedaRama();
}

function _pathnameIsRamaDashboard(pathname) {
  return /\/dashboard\/rama\/?$/.test(String(pathname || ""));
}

function colapsarArbolRamaDashboard() {
  expandAll(false);
  _persistRamaDashboardState();
}

function _bindRamaDashboardTabCollapse() {
  if (!_pathnameIsRamaDashboard(window.location.pathname)) return;
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest("a.global-tab, a.global-nav-dd-link");
      if (!a || !a.href) return;
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }
      let hrefPath = "";
      try {
        hrefPath = new URL(a.getAttribute("href") || "", window.location.href).pathname;
      } catch (_err) {
        return;
      }
      if (!_pathnameIsRamaDashboard(hrefPath)) return;
      const isCurrent =
        a.classList.contains("active") || a.classList.contains("global-nav-dd-link--current");
      if (!isCurrent) return;
      e.preventDefault();
      colapsarArbolRamaDashboard();
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    true
  );
}

function setExpanded(el, expanded) {
  el.setAttribute("aria-expanded", expanded ? "true" : "false");
}

function _escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _saveStateSoon() {
  if (_restoringRamaState) return;
  if (!_ramaStateStore) return;
  _ramaStateStore.saveSoon(_buildRamaDashboardStatePayload);
}

function _expandedSiteNames() {
  return Array.from(document.querySelectorAll(".site-head[data-toggle-node][aria-expanded='true']"))
    .map((el) => el.closest(".principal-block")?.getAttribute("data-principal-name") || "")
    .map((s) => s.trim())
    .filter(Boolean);
}

function _expandedRamas() {
  return Array.from(document.querySelectorAll(".rama-row[data-toggle-node][aria-expanded='true']"))
    .map((el) => el.closest("[data-rama-card]")?.getAttribute("data-rama") || "")
    .map((s) => s.trim())
    .filter(Boolean);
}

function _expandedCtoKeys() {
  return Array.from(document.querySelectorAll("[data-cto-node][aria-expanded='true']"))
    .map((el) => {
      const cto = (el.getAttribute("data-cto") || "").trim();
      const rama = (el.closest("[data-rama-card]")?.getAttribute("data-rama") || "").trim();
      if (!cto || !rama) return "";
      return rama + "||" + cto;
    })
    .filter(Boolean);
}

function _buildRamaDashboardStatePayload() {
  const input = document.getElementById("q");
  return {
    q: String(input?.value || "").trim(),
    expandedSite: Array.from(new Set(_expandedSiteNames())),
    expandedRama: Array.from(new Set(_expandedRamas())),
    expandedCto: Array.from(new Set(_expandedCtoKeys())),
    scrollY: Math.max(0, Math.floor(window.scrollY || 0)),
    ts: Date.now(),
  };
}

function _persistRamaDashboardState() {
  if (_restoringRamaState || !_ramaStateStore) return;
  _ramaStateStore.save(_buildRamaDashboardStatePayload);
}

function _readRamaDashboardState() {
  if (!_ramaStateStore) return null;
  return _ramaStateStore.read((parsed) => {
    if (!parsed || typeof parsed !== "object") return null;
    return {
      q: typeof parsed.q === "string" ? parsed.q : "",
      expandedSite: Array.isArray(parsed.expandedSite) ? parsed.expandedSite.filter((x) => typeof x === "string") : [],
      expandedRama: Array.isArray(parsed.expandedRama) ? parsed.expandedRama.filter((x) => typeof x === "string") : [],
      expandedCto: Array.isArray(parsed.expandedCto) ? parsed.expandedCto.filter((x) => typeof x === "string") : [],
      scrollY: Number.isFinite(parsed.scrollY) ? Number(parsed.scrollY) : 0,
    };
  });
}

function _expandSiteByName(siteName) {
  const target = String(siteName || "").trim();
  if (!target) return;
  document.querySelectorAll(".principal-block").forEach((pb) => {
    const name = (pb.getAttribute("data-principal-name") || "").trim();
    if (name !== target) return;
    const head = pb.querySelector(":scope > .site-head[data-toggle-node]");
    const body = head?.nextElementSibling;
    if (head && body) {
      body.classList.remove("hidden");
      setExpanded(head, true);
    }
  });
}

async function _expandRamaByValueEnsuringInventory(ramaVal) {
  const target = String(ramaVal || "").trim();
  if (!target) return;
  const card = Array.from(document.querySelectorAll("[data-rama-card]")).find(
    (el) => String(el.getAttribute("data-rama") || "").trim() === target
  );
  if (!card) return;
  const pb = card.closest(".principal-block");
  const siteHead = pb?.querySelector(":scope > .site-head[data-toggle-node]");
  const siteBody = siteHead?.nextElementSibling;
  if (siteHead && siteBody) {
    siteBody.classList.remove("hidden");
    setExpanded(siteHead, true);
  }
  const row = card.querySelector(".rama-row[data-toggle-node]");
  const body = row?.nextElementSibling;
  if (row && body) {
    const container = card.querySelector("[data-rama-detail]");
    if (container) {
      await cargarInventarioRama(target, card, container);
    }
    body.classList.remove("hidden");
    setExpanded(row, true);
  }
}

function _expandCtoByKey(key) {
  const raw = String(key || "");
  const sep = raw.indexOf("||");
  if (sep < 0) return;
  const rama = raw.slice(0, sep).trim();
  const cto = raw.slice(sep + 2).trim();
  if (!rama || !cto) return;
  document.querySelectorAll("[data-rama-card]").forEach((card) => {
    const ramaVal = (card.getAttribute("data-rama") || "").trim();
    if (ramaVal !== rama) return;
    const row = card.querySelector(".rama-row[data-toggle-node]");
    const body = row?.nextElementSibling;
    if (row && body) {
      body.classList.remove("hidden");
      setExpanded(row, true);
    }
    card.querySelectorAll("[data-cto-node]").forEach((ctoNode) => {
      const ctoVal = (ctoNode.getAttribute("data-cto") || "").trim();
      if (ctoVal !== cto) return;
      const ctoBody = ctoNode.nextElementSibling;
      if (ctoBody) {
        ctoBody.classList.remove("hidden");
        setExpanded(ctoNode, true);
        _scheduleCtoMapIfExpanded(ctoNode);
      }
    });
  });
}

async function restoreRamaDashboardState(preQ) {
  const forceCollapsedByTabSwitch =
    !!(window.consumeDashboardTabForceCollapse && window.consumeDashboardTabForceCollapse("/dashboard/rama"));
  if (forceCollapsedByTabSwitch) {
    try {
      sessionStorage.removeItem(_RAMA_STATE_KEY);
    } catch (_err) {}
  }
  const state = _readRamaDashboardState();
  const input = document.getElementById("q");
  if (input) {
    if (preQ) input.value = preQ;
    else if (state?.q && !forceCollapsedByTabSwitch) input.value = state.q;
    else if (forceCollapsedByTabSwitch) input.value = "";
  }

  _restoringRamaState = true;
  try {
    aplicarFiltro();
    if (forceCollapsedByTabSwitch) {
      expandAll(false);
      return;
    }
    if (!state) return;
    state.expandedSite.forEach(_expandSiteByName);
    for (const rama of state.expandedRama) {
      await _expandRamaByValueEnsuringInventory(rama);
    }
    state.expandedCto.forEach(_expandCtoByKey);
    aplicarFiltro();
  } finally {
    _restoringRamaState = false;
  }

  if (state && _ramaStateStore) _ramaStateStore.restoreScroll(state.scrollY);
}

const _RAMA_CTO_MAP_URL = "/dashboard/rama/cto-map";
const _RAMA_MAP_URL = "/dashboard/rama/rama-map";

function _scheduleCtoMapIfExpanded(ctoNode) {
  if (!ctoNode) return;
  queueMicrotask(() => ensureCtoMapForCtoNode(ctoNode));
}

function ensureCtoMapForCtoNode(ctoNode) {
  if (!ctoNode || !ctoNode.hasAttribute("data-cto-node")) return;
  const body = ctoNode.nextElementSibling;
  if (!body || body.classList.contains("hidden")) return;
  const shell = body.querySelector("[data-cto-map-shell]");
  if (!shell) return;
  const status = shell.dataset.mapReady;
  if (status === "done" || status === "nocords") return;
  if (status === "loading") return;
  const cto = (ctoNode.getAttribute("data-cto") || "").trim();
  if (!cto) return;

  const msg = shell.querySelector(".rama-cto-map-msg");
  const canvas = shell.querySelector(".rama-cto-map-canvas");
  if (!msg || !canvas) return;

  shell.dataset.mapReady = "loading";
  msg.textContent = "Cargando ubicación…";
  canvas.hidden = true;

  fetch(_RAMA_CTO_MAP_URL + "?cto=" + encodeURIComponent(cto))
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      if (!data || !data.ok) {
        msg.textContent = (data && data.error) || "Sin coordenadas para esta CTO";
        canvas.hidden = true;
        shell.dataset.mapReady = "nocords";
        return;
      }
      if (typeof window.L === "undefined") {
        msg.textContent = "No se pudo cargar el mapa (Leaflet).";
        canvas.hidden = true;
        shell.dataset.mapReady = "nocords";
        return;
      }
      const lat = Number(data.lat);
      const lon = Number(data.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        msg.textContent = "Sin coordenadas para esta CTO";
        canvas.hidden = true;
        shell.dataset.mapReady = "nocords";
        return;
      }
      msg.textContent = "";
      canvas.hidden = false;

      if (!shell._leafletMap) {
        const map = window.L.map(canvas, { attributionControl: true, zoomControl: true }).setView([lat, lon], 17);
        if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
          shell._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
        } else {
          window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
          }).addTo(map);
        }
        window.L.marker([lat, lon]).addTo(map);
        shell._leafletMap = map;
        requestAnimationFrame(() => {
          map.invalidateSize();
        });
      }
      shell.dataset.mapReady = "done";
    })
    .catch(() => {
      msg.textContent = "No se pudo obtener la ubicación.";
      canvas.hidden = true;
      delete shell.dataset.mapReady;
    });
}

function verMapaRama(btn) {
  if (!btn) return;
  const card = btn.closest("[data-rama-card]");
  if (!card) return;
  const rama = (card.getAttribute("data-rama") || "").trim();
  if (!rama) return;

  const panel = card.querySelector("[data-rama-map-panel]");
  const ramaRow = card.querySelector(".rama-row[data-toggle-node]");
  const indent2 = ramaRow ? ramaRow.nextElementSibling : null;
  const detail = card.querySelector("[data-rama-detail]");
  if (!panel || !indent2 || !detail) return;

  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    btn.textContent = "Ver mapa";
    btn.setAttribute("aria-expanded", "false");
    _saveStateSoon();
    return;
  }

  const openPanel = () => {
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    btn.textContent = "Ocultar mapa";
    btn.setAttribute("aria-expanded", "true");
    const labelEl = panel.querySelector("[data-rama-mapa-label]");
    if (labelEl) labelEl.textContent = rama;
    _loadRamaMapPanel(card, rama, panel);
    _saveStateSoon();
  };

  if (indent2.classList.contains("hidden")) {
    cargarInventarioRama(rama, card, detail).finally(() => {
      indent2.classList.remove("hidden");
      if (ramaRow) setExpanded(ramaRow, true);
      openPanel();
    });
    return;
  }

  openPanel();
}

function _loadRamaMapPanel(card, rama, panel) {
  const msg = panel.querySelector(".rama-mapa-msg");
  const footer = panel.querySelector(".rama-mapa-footer");
  const canvas = panel.querySelector("[data-rama-mapa-canvas]");
  if (!msg || !canvas) return;

  msg.textContent = "Cargando mapa…";
  if (footer) footer.textContent = "";
  canvas.hidden = true;

  fetch(_RAMA_MAP_URL + "?rama=" + encodeURIComponent(rama))
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      if (!data || !data.ok) {
        msg.textContent = (data && data.error) || "No se pudo cargar el mapa de la RAMA.";
        canvas.hidden = true;
        return;
      }
      const markers = Array.isArray(data.markers) ? data.markers : [];
      const sinCoord =
        data.ctos_sin_coordenadas != null ? Number(data.ctos_sin_coordenadas) : 0;
      const ctosTotal = data.ctos_total != null ? Number(data.ctos_total) : 0;

      if (markers.length === 0) {
        if (ctosTotal === 0) {
          msg.textContent = "No hay CTO en inventario para esta RAMA.";
        } else {
          msg.textContent = "Ninguna CTO de esta RAMA tiene coordenadas cargadas.";
        }
        canvas.hidden = true;
        if (footer) {
          footer.textContent = sinCoord > 0 ? `${sinCoord} CTO sin coordenadas.` : "";
        }
        return;
      }

      msg.textContent = "";
      canvas.hidden = false;
      if (footer) {
        let foot = `${markers.length} CTO en el mapa`;
        if (sinCoord > 0) foot += ` · ${sinCoord} sin coordenadas`;
        footer.textContent = foot + ".";
      }

      if (typeof window.L === "undefined") {
        msg.textContent = "No se pudo cargar el mapa (Leaflet).";
        canvas.hidden = true;
        return;
      }

      let map = panel._ramaLeafletMap;
      if (!map) {
        map = window.L.map(canvas, { attributionControl: true, zoomControl: true });
        if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
          panel._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
        } else {
          window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
          }).addTo(map);
        }
        panel._ramaLeafletMap = map;
      }

      if (panel._ramaMarkerLayer) {
        map.removeLayer(panel._ramaMarkerLayer);
        panel._ramaMarkerLayer = null;
      }

      const fg = window.L.featureGroup();
      markers.forEach((mk) => {
        const lat = Number(mk.lat);
        const lon = Number(mk.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const marker = window.L.marker([lat, lon]);
        marker.bindPopup('<span class="mono">' + _escHtml(mk.cto || "") + "</span>", { maxWidth: 320 });
        fg.addLayer(marker);
      });

      if (fg.getLayers().length === 0) {
        msg.textContent = "Coordenadas inválidas en la respuesta.";
        canvas.hidden = true;
        return;
      }

      fg.addTo(map);
      panel._ramaMarkerLayer = fg;

      requestAnimationFrame(() => {
        map.invalidateSize();
        const bounds = fg.getBounds();
        if (markers.length === 1) {
          map.setView(bounds.getCenter(), 17);
        } else {
          map.fitBounds(bounds, { padding: [28, 28], maxZoom: 17 });
        }
      });
    })
    .catch(() => {
      msg.textContent = "No se pudo cargar el mapa.";
      canvas.hidden = true;
    });
}

function toggle(el) {
  const next = el.nextElementSibling;
  if (!next) return;
  const card = el.closest("[data-rama-card]");
  const rama = (card?.getAttribute("data-rama") || "").trim();
  const isRamaRow = el.classList.contains("rama-row");
  const willExpand = next.classList.contains("hidden");
  if (willExpand && isRamaRow && card) {
    const container = card.querySelector("[data-rama-detail]");
    if (container) {
      cargarInventarioRama(rama, card, container).finally(() => {
        next.classList.remove("hidden");
        setExpanded(el, true);
        _saveStateSoon();
      });
      return;
    }
  }
  next.classList.toggle("hidden");
  setExpanded(el, willExpand);
  if (willExpand && el.hasAttribute("data-cto-node") && !isRamaRow) {
    _scheduleCtoMapIfExpanded(el);
    _autoConsultarCtoPotenciasAlExpandir(el);
  }
  _saveStateSoon();
}

function expandAll(open) {
  document.querySelectorAll("[data-toggle-node]").forEach((n) => {
    const next = n.nextElementSibling;
    if (!next) return;
    if (open) {
      next.classList.remove("hidden");
    } else {
      next.classList.add("hidden");
    }
    setExpanded(n, open);
  });
}

function clearSearchHighlights() {
  document.querySelectorAll(".search-hit-cto").forEach((el) => el.classList.remove("search-hit-cto"));
  document.querySelectorAll(".search-hit-rama").forEach((el) => el.classList.remove("search-hit-rama"));
}

function applySearchHighlights(qn) {
  clearSearchHighlights();
  if (!qn) return;
  document.querySelectorAll("[data-rama-card].filter-match").forEach((card) => {
    if (card.style.display === "none") return;
    const rama = (card.getAttribute("data-rama") || "").toLowerCase();
    const ctos = (card.getAttribute("data-ctos") || "").toLowerCase();
    const ramaRow = card.querySelector(".rama-row[data-toggle-node]");

    if (rama.includes(qn)) {
      ramaRow?.classList.add("search-hit-rama");
    }
    if (ctos.includes(qn)) {
      ramaRow?.classList.add("search-hit-rama");
      card.querySelectorAll("[data-cto-node]").forEach((node) => {
        const cto = (node.getAttribute("data-cto") || "").trim().toLowerCase();
        if (cto && (cto.includes(qn) || (qn.length >= cto.length && qn.includes(cto)))) {
          node.classList.add("search-hit-cto");
        }
      });
    }
  });
}

function expandPathToCard(card, q) {
  if (!card) return;
  const qn = (q || "").trim().toLowerCase();
  const pb = card.closest(".principal-block");
  const siteHead = pb?.querySelector(":scope > .site-head");
  const siteBody = siteHead?.nextElementSibling;
  if (siteHead && siteBody) {
    siteBody.classList.remove("hidden");
    setExpanded(siteHead, true);
  }
  const ramaRow = card.querySelector(".rama-row[data-toggle-node]");
  const ramaBody = ramaRow?.nextElementSibling;
  if (ramaRow && ramaBody) {
    ramaBody.classList.remove("hidden");
    setExpanded(ramaRow, true);
  }
  if (!qn) return;
  const ctos = (card.getAttribute("data-ctos") || "").toLowerCase();
  const matchCto = ctos.includes(qn);
  if (!matchCto) return;
  card.querySelectorAll("[data-cto-node]").forEach((ctoNode) => {
    const body = ctoNode.nextElementSibling;
    if (body) {
      body.classList.remove("hidden");
      setExpanded(ctoNode, true);
      _scheduleCtoMapIfExpanded(ctoNode);
    }
  });
}

function aplicarFiltro() {
  const raw = (document.getElementById("q")?.value || "").trim();
  const q = raw.toLowerCase();
  const rows = document.querySelectorAll("[data-rama-card]");
  const counter = document.getElementById("visibleCount");

  if (!q) {
    clearSearchHighlights();
    document.querySelectorAll(".principal-block").forEach((pb) => {
      pb.style.display = "";
    });
    rows.forEach((card) => {
      card.style.display = "";
      card.classList.remove("filter-match");
    });
    if (counter) counter.textContent = `${rows.length} RAMAs`;
    _lastJumpKey = "";
    document.querySelectorAll(".rama-row.is-target").forEach((el) => el.classList.remove("is-target"));
    _saveStateSoon();
    return;
  }

  expandAll(false);
  clearSearchHighlights();

  let visible = 0;
  let firstMatch = null;

  rows.forEach((card) => {
    const rama = (card.getAttribute("data-rama") || "").toLowerCase();
    const ctos = (card.getAttribute("data-ctos") || "").toLowerCase();
    const pb = card.closest(".principal-block");
    const pname = (pb?.getAttribute("data-principal-name") || "").toLowerCase();
    const ok = rama.includes(q) || ctos.includes(q) || pname.includes(q);
    card.style.display = ok ? "" : "none";
    card.classList.toggle("filter-match", ok);
    if (ok) {
      visible++;
      if (!firstMatch) firstMatch = card;
      expandPathToCard(card, q);
    }
  });

  document.querySelectorAll(".principal-block").forEach((pb) => {
    const any = pb.querySelector("[data-rama-card].filter-match");
    pb.style.display = any ? "" : "none";
  });

  applySearchHighlights(q);

  if (counter) counter.textContent = `${visible} RAMAs`;

  if (q && visible === 1 && firstMatch) {
    scheduleJump(q, firstMatch);
  }
  _saveStateSoon();
}

function scheduleJump(key, card) {
  if (_jumpTimer) clearTimeout(_jumpTimer);
  _jumpTimer = setTimeout(() => jumpToCard(key, card), 220);
}

function jumpToCard(key, card) {
  if (!card) return;
  if (_lastJumpKey === key) return;
  _lastJumpKey = key;

  const q = (document.getElementById("q")?.value || "").trim().toLowerCase();
  expandPathToCard(card, q);

  const ramaRow = card.querySelector(".rama-row[data-toggle-node]");
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  document.querySelectorAll(".rama-row.is-target").forEach((el) => el.classList.remove("is-target"));
  if (ramaRow) ramaRow.classList.add("is-target");

  const btn = card.querySelector("button.btn");
  if (btn) btn.focus({ preventScroll: true });
}

function _parseRx(text) {
  if (text == null) return null;
  const s = String(text).trim().replace(",", ".").replace(/dbm$/i, "").trim();
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

function _formatPowerDbm(v) {
  if (v === null || v === undefined) return "-";
  const raw = String(v).trim();
  if (!raw || raw === "-" || raw === "⏳") return raw || "-";
  if (/dbm$/i.test(raw)) return raw;
  return raw + " dBm";
}

function _clasePorRx(rx) {
  if (rx == null) return null;
  if (rx < -27) return "rx-warn";
  if (rx <= -25) return "rx-alert";
  return null;
}

function _aplicarResaltadoFila(tr, rxText) {
  tr.classList.remove("rx-warn", "rx-alert");
  const rx = _parseRx(rxText);
  const cls = _clasePorRx(rx);
  if (cls) tr.classList.add(cls);
}

function _hasPowerRama(v) {
  return !(v === null || v === undefined || String(v).trim() === "" || String(v).trim() === "-");
}

function _ramaRowCellsHtml(o, rama, cto, outNum) {
  const st = String(o.STATUS || "").trim().toUpperCase();
  const aidDisp = st === "FREE" ? "-" : _escHtml(o.AID);
  const opDisp = st === "FREE" ? "-" : _escHtml(o.OPERADOR);
  const principal = _escHtml(o.PRINCIPAL || "—");
  const ramaDisp = _escHtml(o.RAMA || rama || "—");
  const ontRaw = (o.ONT || "").trim();
  const ontDisp = st === "FREE" ? "" : _escHtml(ontRaw || "—");
  const statusDisp = _escHtml(o.STATUS || "");
  const spin =
    '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';

  let txCell;
  let rxCell;
  let estCell;
  if (st === "FREE") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
    estCell = '<td class="mono">-</td>';
  } else if (st === "RESERVED") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
    estCell = '<td class="mono status-down">DOWN</td>';
  } else {
    txCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    rxCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    estCell = '<td class="mono status-pending">Cargando...</td>';
  }

  return `
            <td class="mono">${outNum}</td>
            <td class="mono">${aidDisp}</td>
            <td>${opDisp}</td>
            <td>${principal}</td>
            <td class="mono">${ramaDisp}</td>
            <td class="mono">${ontDisp}</td>
            <td>${statusDisp}</td>
            ${txCell}
            ${rxCell}
            ${estCell}
  `;
}

function renderInventarioRama(rama, inv, container) {
  const ctos = Object.keys(inv || {}).sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }));
  let html = `
    <p class="hint rama-hint-no-margin">
      <label class="rama-cto-select-all-label">
        <input type="checkbox" class="cto-select-all-in-rama" title="Marcar todas las CTO de esta RAMA" aria-label="Seleccionar todas las CTO de esta RAMA">
        Seleccionar todas las CTO de esta RAMA
      </label>
    </p>
  `;

  ctos.forEach((cto) => {
    const onts = inv[cto] || [];
    html += `
      <div class="node indent2 cto-head-row" data-toggle-node data-cto-node data-cto="${_escHtml(cto)}" aria-expanded="false" onclick="toggle(this)">
        <input type="checkbox" class="cto-select" title="Seleccionar CTO para exportación" aria-label="Seleccionar CTO" onclick="event.stopPropagation()">
        <span class="rama-row-kind rama-row-kind--cto">CTO</span>
        <span class="arrow">▶</span>
        <span class="mono rama-row-label">${_escHtml(cto)}</span>
        <span class="rama-row-actions" onclick="event.stopPropagation()">
          <button type="button" class="btn-mini pot-cto" data-pot-cto="${encodeURIComponent(cto)}">Consultar</button>
        </span>
      </div>
      <div class="hidden indent3">
        <div class="rama-cto-map-shell" data-cto-map-shell data-cto="${_escHtml(cto)}">
          <p class="hint rama-cto-map-msg" aria-live="polite"></p>
          <div class="rama-cto-map-canvas" hidden></div>
        </div>
        <div class="table-wrap">
          <table>
            <tr><th>OUT</th><th>AID</th><th>Operador</th><th>Sitio</th><th>RAMA</th><th>ONT</th><th>Status</th><th>TX (dBm)</th><th>RX (dBm)</th><th>Estado</th></tr>
    `;
    onts.forEach((o, oix) => {
      html += `
            <tr data-rama="${_escHtml(rama)}" data-cto="${_escHtml(cto)}" data-aid="${_escHtml(o.AID)}" data-fat-status="${_escHtml(o.STATUS || "")}">
              ${_ramaRowCellsHtml(o, rama, cto, oix + 1)}
            </tr>
      `;
    });
    html += `
          </table>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
  container.querySelectorAll(".cto-select-all-in-rama").forEach((master) => {
    master.addEventListener("change", () => {
      const card = master.closest("[data-rama-card]");
      if (!card) return;
      const on = master.checked;
      card.querySelectorAll(".cto-select").forEach((cb) => {
        cb.checked = on;
      });
    });
  });
  container.querySelectorAll("button.pot-cto").forEach((btnCto) => {
    btnCto.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const ctoNode = btnCto.closest("[data-cto-node]");
      const card = btnCto.closest("[data-rama-card]");
      if (card && ctoNode) {
        _expandOnlyTargetCtoInCard(card, ctoNode);
      }
      consultarCtoRama(decodeURIComponent(btnCto.getAttribute("data-pot-cto") || ""), btnCto);
    });
  });
}

function cargarInventarioRama(rama, card, container) {
  const ramaKey = String(rama || "").trim().toUpperCase();
  if (!ramaKey) return Promise.resolve();
  if (_ramaInventarioCargado[ramaKey]) return Promise.resolve();
  if (_ramaInventarioCargando[ramaKey]) return _ramaInventarioCargando[ramaKey];

  container.innerHTML = '<p class="hint">Cargando inventario de red…</p>';
  const req = fetch("/dashboard/rama/inventario", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "rama=" + encodeURIComponent(rama),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((inv) => {
      renderInventarioRama(rama, inv || {}, container);
      _ramaInventarioCargado[ramaKey] = true;
      card.setAttribute("data-ctos", Object.keys(inv || {}).join(" "));
    })
    .catch(() => {
      container.innerHTML = '<p class="hint">No se pudo cargar inventario. Reintentá.</p>';
    })
    .finally(() => {
      delete _ramaInventarioCargando[ramaKey];
    });
  _ramaInventarioCargando[ramaKey] = req;
  return req;
}

function _expandRamaCardAndEnsureInventory(card, rama) {
  if (!card) return Promise.resolve();
  const ramaRow = card.querySelector(".rama-row[data-toggle-node]");
  const ramaBody = ramaRow ? ramaRow.nextElementSibling : null;
  const detail = card.querySelector("[data-rama-detail]");
  const parentBlock = card.closest(".principal-block");
  const siteHead = parentBlock ? parentBlock.querySelector(":scope > .site-head[data-toggle-node]") : null;
  const siteBody = siteHead ? siteHead.nextElementSibling : null;

  if (siteHead && siteBody) {
    siteBody.classList.remove("hidden");
    setExpanded(siteHead, true);
  }
  if (ramaRow && ramaBody) {
    ramaBody.classList.remove("hidden");
    setExpanded(ramaRow, true);
  }
  if (!detail) return Promise.resolve();
  return cargarInventarioRama(rama, card, detail);
}

function _expandAllCtosInRamaCard(card) {
  if (!card) return;
  card.querySelectorAll("[data-cto-node]").forEach((ctoNode) => {
    const ctoBody = ctoNode.nextElementSibling;
    if (!ctoBody) return;
    ctoBody.classList.remove("hidden");
    setExpanded(ctoNode, true);
    _scheduleCtoMapIfExpanded(ctoNode);
  });
}

function _expandOnlyTargetCtoInCard(card, targetNode) {
  if (!card || !targetNode) return;
  card.querySelectorAll("[data-cto-node]").forEach((ctoNode) => {
    const ctoBody = ctoNode.nextElementSibling;
    if (!ctoBody) return;
    const isTarget = ctoNode === targetNode;
    ctoBody.classList.toggle("hidden", !isTarget);
    setExpanded(ctoNode, isTarget);
    if (isTarget) {
      _scheduleCtoMapIfExpanded(ctoNode);
    }
  });
}

function _setTxRxCellLoading(td, loading) {
  if (!td) return;
  if (loading) {
    td.setAttribute("aria-busy", "true");
    td.setAttribute("aria-label", "Cargando");
    td.classList.add("olt-txrx-cell--loading");
    td.innerHTML =
      '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';
    return;
  }
  td.classList.remove("olt-txrx-cell--loading");
  td.removeAttribute("aria-busy");
  td.removeAttribute("aria-label");
  td.textContent = "-";
}

function _clearTxRxCellLoadingKeepValue(td) {
  if (!td) return;
  td.classList.remove("olt-txrx-cell--loading");
  td.removeAttribute("aria-busy");
  td.removeAttribute("aria-label");
}

function _setRamaCardTxRxCellsLoading(card) {
  if (!card) {
    return;
  }
  card.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (_ramaFatSkipPotencias(tr)) return;
    _setTxRxCellLoading(tr.children[RAMA_COL_TX], true);
    _setTxRxCellLoading(tr.children[RAMA_COL_RX], true);
  });
}

function _ramaCardTxRxCellsStuckToDash(card) {
  if (!card) {
    return;
  }
  card.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (tr.children[RAMA_COL_TX] && tr.children[RAMA_COL_TX].classList.contains("olt-txrx-cell--loading")) {
      _setTxRxCellLoading(tr.children[RAMA_COL_TX], false);
    }
    if (tr.children[RAMA_COL_RX] && tr.children[RAMA_COL_RX].classList.contains("olt-txrx-cell--loading")) {
      _setTxRxCellLoading(tr.children[RAMA_COL_RX], false);
    }
  });
}

function _aplicarDataRama(rama, data, row, card) {
  const res = data.__dashboard_resumen__;
  if (res && row) {
    const elR = row.querySelector('[data-semaforo="rojo"]');
    const elA = row.querySelector('[data-semaforo="amarillo"]');
    const elV = row.querySelector('[data-semaforo="verde"]');
    if (elR) elR.textContent = res.ROJAS;
    if (elA) elA.textContent = res.AMARILLAS;
    if (elV) elV.textContent = res.VERDES;
  }
  const root = card || document;
  root.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if ((tr.getAttribute("data-rama") || "") !== String(rama)) return;
    const cto = tr.dataset.cto;
    const aid = tr.dataset.aid;
    if (_ramaFatSkipPotencias(tr)) return;
    const tdTx = tr.children[RAMA_COL_TX];
    const tdRx = tr.children[RAMA_COL_RX];
    const tdEst = tr.children[RAMA_COL_EST];
    if (!tdTx || !tdRx) {
      return;
    }
    if (data[cto] && data[cto][aid]) {
      _clearTxRxCellLoadingKeepValue(tdTx);
      _clearTxRxCellLoadingKeepValue(tdRx);
      tdTx.innerText = _formatPowerDbm(data[cto][aid].TX);
      tdRx.innerText = _formatPowerDbm(data[cto][aid].RX);
      _aplicarResaltadoFila(tr, tdRx.innerText);
      if (tdEst) {
        tdEst.classList.remove("status-pending");
        const up = _hasPowerRama(data[cto][aid].TX) || _hasPowerRama(data[cto][aid].RX);
        tdEst.textContent = up ? "UP" : "DOWN";
        tdEst.classList.remove("status-up", "status-down");
        tdEst.classList.add(up ? "status-up" : "status-down");
      }
    }
  });
}

function _setRamaPotButtonLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    if (!btn.dataset.potLabel) btn.dataset.potLabel = (btn.textContent || "").trim() || "Consultar";
    btn.disabled = true;
    btn.classList.add("pot-btn-loading");
    btn.innerHTML = "";
    const inner = document.createElement("span");
    inner.className = "pot-btn-loading-inner";
    const sp = document.createElement("span");
    sp.className = "pot-txrx-spin";
    sp.setAttribute("aria-hidden", "true");
    const lab = document.createElement("span");
    lab.className = "pot-txrx-label";
    lab.textContent = "Cargando TX/RX";
    inner.appendChild(sp);
    inner.appendChild(lab);
    btn.appendChild(inner);
    btn.setAttribute("aria-busy", "true");
  } else {
    btn.disabled = false;
    btn.classList.remove("pot-btn-loading");
    btn.removeAttribute("aria-busy");
    btn.textContent = btn.dataset.potLabel || "Consultar";
  }
}

function _autoConsultarCtoPotenciasAlExpandir(ctoNode) {
  const ctoBody = ctoNode.nextElementSibling;
  if (!ctoBody || !_ctoBodyTieneFilasPendientesPotencias(ctoBody)) return;
  const cto = (ctoNode.getAttribute("data-cto") || "").trim();
  const card = ctoNode.closest("[data-rama-card]");
  if (!cto || !card) return;
  _ejecutarConsultaPotenciasCto(cto, ctoNode, card, null, { silentToast: true });
}

function _ejecutarConsultaPotenciasCto(cto, ctoNode, card, feedbackBtn, opts) {
  opts = opts || {};
  const silentToast = opts.silentToast === true;
  const ctoBody = ctoNode.nextElementSibling;
  if (!cto || !card || !ctoBody) {
    return Promise.resolve();
  }

  const existing = ctoNode._potCtoFetchPromise;
  if (existing) {
    if (feedbackBtn) {
      _setRamaPotButtonLoading(feedbackBtn, true);
      existing.finally(() => _setRamaPotButtonLoading(feedbackBtn, false));
    }
    return existing;
  }

  if (feedbackBtn) _setRamaPotButtonLoading(feedbackBtn, true);
  ctoBody.classList.remove("hidden");
  setExpanded(ctoNode, true);
  _scheduleCtoMapIfExpanded(ctoNode);

  ctoBody.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (_ramaFatSkipPotencias(tr)) return;
    _setTxRxCellLoading(tr.children[RAMA_COL_TX], true);
    _setTxRxCellLoading(tr.children[RAMA_COL_RX], true);
  });

  const p = fetch("/dashboard/cto/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "cto=" + encodeURIComponent(cto),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((rows) => {
      if (!Array.isArray(rows)) return;
      rows.forEach((rec) => {
        const aid = String(rec.AID || "");
        if (!aid) return;
        const tr = _findTrByAidInCtoBody(ctoBody, aid);
        if (!tr || _ramaFatSkipPotencias(tr)) return;
        const tdTx = tr.children[RAMA_COL_TX];
        const tdRx = tr.children[RAMA_COL_RX];
        const tdEst = tr.children[RAMA_COL_EST];
        if (!tdTx || !tdRx) return;
        _clearTxRxCellLoadingKeepValue(tdTx);
        _clearTxRxCellLoadingKeepValue(tdRx);
        tdTx.innerText = _formatPowerDbm(rec.TX);
        tdRx.innerText = _formatPowerDbm(rec.RX);
        _aplicarResaltadoFila(tr, tdRx.innerText);
        if (tdEst) {
          tdEst.classList.remove("status-pending");
          const up = _hasPowerRama(rec.TX) || _hasPowerRama(rec.RX);
          tdEst.textContent = up ? "UP" : "DOWN";
          tdEst.classList.remove("status-up", "status-down");
          tdEst.classList.add(up ? "status-up" : "status-down");
        }
      });
      _saveStateSoon();
      if (!silentToast) {
        toast(`Potencias actualizadas CTO: ${cto}`);
      }
    })
    .catch(() => {
      toast(`Error consultando potencias CTO: ${cto}`);
    })
    .finally(() => {
      ctoBody.querySelectorAll("tr[data-aid]").forEach((tr) => {
        if (tr.children[RAMA_COL_TX] && tr.children[RAMA_COL_TX].classList.contains("olt-txrx-cell--loading")) {
          _setTxRxCellLoading(tr.children[RAMA_COL_TX], false);
        }
        if (tr.children[RAMA_COL_RX] && tr.children[RAMA_COL_RX].classList.contains("olt-txrx-cell--loading")) {
          _setTxRxCellLoading(tr.children[RAMA_COL_RX], false);
        }
      });
      if (feedbackBtn) _setRamaPotButtonLoading(feedbackBtn, false);
      if (ctoNode._potCtoFetchPromise === p) {
        delete ctoNode._potCtoFetchPromise;
      }
    });

  ctoNode._potCtoFetchPromise = p;
  return p;
}

function consultarCtoRama(cto, btn) {
  const ctoNode = btn ? btn.closest("[data-cto-node]") : null;
  const card = btn ? btn.closest("[data-rama-card]") : null;
  const ctoBody = ctoNode ? ctoNode.nextElementSibling : null;
  if (!cto || !card || !ctoBody) {
    return;
  }
  _ejecutarConsultaPotenciasCto(cto, ctoNode, card, btn, {});
}

function consultarRama(rama, btn) {
  const row = btn.closest(".rama-row");
  const card = row ? row.closest("[data-rama-card]") : null;
  const ejecutarConsulta = () => {
    const cacheKey = String(rama || "").trim().toUpperCase();
    const cached = _ramaPotenciasCache[cacheKey];
    if (cached && (Date.now() - cached.ts) < _ramaPotenciasCacheMs) {
      _aplicarDataRama(rama, cached.data, row, card);
      toast(`Potencias (cache): ${rama}`);
      _saveStateSoon();
      return;
    }

    _setRamaPotButtonLoading(btn, true);
    if (card) {
      _setRamaCardTxRxCellsLoading(card);
    }

    fetch("/dashboard/rama/consultar", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "rama=" + encodeURIComponent(rama),
    })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((data) => {
        _ramaPotenciasCache[cacheKey] = { ts: Date.now(), data };
        _aplicarDataRama(rama, data, row, card);
        toast(`Potencias actualizadas: ${rama}`);
        _saveStateSoon();
      })
      .catch(() => {
        toast(`Error consultando potencias: ${rama}`);
      })
      .finally(() => {
        if (card) {
          _ramaCardTxRxCellsStuckToDash(card);
        }
        _setRamaPotButtonLoading(btn, false);
      });
  };

  _expandRamaCardAndEnsureInventory(card, rama).then(() => {
    _expandAllCtosInRamaCard(card);
    _saveStateSoon();
    ejecutarConsulta();
  });
}

window.addEventListener("load", () => {
  const input = document.getElementById("q");
  const pre = new URLSearchParams(window.location.search).get("q");
  restoreRamaDashboardState(pre);
  _bindRamaDashboardTabCollapse();
  if (input) {
    input.addEventListener("input", () => {
      _lastJumpKey = "";
      aplicarFiltro();
    });

    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const q = (input.value || "").trim().toLowerCase();
      const first = Array.from(document.querySelectorAll("[data-rama-card]")).find(c => c.style.display !== "none");
      if (q && first) jumpToCard(q, first);
    });
  }

  document.querySelectorAll("a[href^='/dashboard/potencias-historico']").forEach((a) => {
    a.addEventListener("click", () => _persistRamaDashboardState());
  });

  window.addEventListener("pagehide", () => _persistRamaDashboardState());
  window.addEventListener("beforeunload", () => _persistRamaDashboardState());
  window.addEventListener("scroll", _saveStateSoon, { passive: true });

  if (window.initNocPage) {
    initNocPage({
      page: "rama",
      searchSelector: "#q",
      onClear: function () {
        const el = document.getElementById("q");
        if (el) el.value = "";
        if (typeof aplicarFiltro === "function") aplicarFiltro();
      },
      onSearchChange: function () {
        if (typeof aplicarFiltro === "function") aplicarFiltro();
      },
    });
  }

});
