let _toastTimer = null;
let _jumpTimer = null;
let _filtroRamaTimer = null;
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

/** Columnas tabla CTO: OUT…RX (sin SN ni columna Estado). */
const RAMA_COL_TX = 7;
const RAMA_COL_RX = 8;

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
    ["Sitio_principal", "RAMA", "CTO", "OUT", "AID", "Operador", "SITIO", "ONT", "STATUS", "TX", "RX"].join(
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

function limpiarSeleccionCtoRama() {
  document.querySelectorAll(".cto-select, .cto-select-all-in-rama").forEach((cb) => {
    cb.checked = false;
  });
}

function colapsarTodoYLimpiarRama() {
  expandAll(false);
  limpiarBusquedaRama();
  limpiarSeleccionCtoRama();
  _persistRamaDashboardState();
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
  if (window.__ramaDashboardTabCollapseBound) return;
  window.__ramaDashboardTabCollapseBound = true;
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
  if (el.classList.contains("site-head")) {
    el.classList.toggle("site-head-accent", expanded);
  } else if (el.classList.contains("rama-row")) {
    el.classList.toggle("rama-row-accent", expanded);
  } else if (el.hasAttribute("data-cto-node")) {
    el.classList.toggle("cto-row-accent", expanded);
  }
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

function _ramaInventarioLoadingHtml() {
  return (
    '<div class="rama-detail-loading lt-detail-loading" role="status" aria-live="polite" aria-busy="true">' +
    '<span class="rama-detail-spinner lt-detail-spinner" aria-hidden="true"></span>' +
    "<span>Cargando inventario de red…</span></div>"
  );
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
    body.classList.remove("hidden");
    setExpanded(row, true);
    const container = card.querySelector("[data-rama-detail]");
    if (container) {
      await cargarInventarioRama(target, card, container);
    }
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
        ensureCtoAddressForCtoNode(ctoNode);
        _autoConsultarCtoPotenciasAlExpandir(ctoNode);
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
    document.querySelectorAll("[data-rama-card]").forEach((card) => {
      _ramaPotenciasParaCtosExpandidosEn(card);
    });
    aplicarFiltro();
  } finally {
    _restoringRamaState = false;
  }

  if (state && _ramaStateStore) _ramaStateStore.restoreScroll(state.scrollY);
}

const _RAMA_CTO_MAP_URL = "/dashboard/rama/cto-map";
const _RAMA_CTO_ADDRESS_URL = "/dashboard/rama/cto-address";
const _RAMA_MAP_URL = "/dashboard/rama/rama-map";
const _RAMA_CAMINO_GIS_URL = "/dashboard/camino-optico/gis";

function _extendBoundsFromGeoJSON(bounds, gj) {
  const depthByType = {
    Point: 0,
    MultiPoint: 1,
    LineString: 1,
    MultiLineString: 2,
    Polygon: 2,
    MultiPolygon: 3,
  };
  function scanPair(lon, lat) {
    if (typeof lon !== "number" || typeof lat !== "number") return;
    if (Number.isNaN(lon) || Number.isNaN(lat)) return;
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
    bounds.extend(window.L.latLng(lat, lon));
  }
  function scan(coords, depth) {
    if (depth === 0) {
      scanPair(coords[0], coords[1]);
      return;
    }
    if (Array.isArray(coords)) coords.forEach((c) => scan(c, depth - 1));
  }
  (gj && gj.features ? gj.features : []).forEach((f) => {
    const g = f && f.geometry;
    if (!g || !g.coordinates) return;
    const d = depthByType[g.type];
    if (d != null) scan(g.coordinates, d);
  });
}

function _fitRamaMapToData(map, gj, markers) {
  const b = window.L.latLngBounds([]);
  if (gj) _extendBoundsFromGeoJSON(b, gj);
  (markers || []).forEach((m) => {
    const lat = Number(m.lat);
    const lon = Number(m.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    b.extend(window.L.latLng(lat, lon));
  });
  if (!b.isValid()) return false;
  try {
    map.fitBounds(b, { padding: [28, 28], maxZoom: 17 });
    return true;
  } catch (_e) {
    return false;
  }
}

function ensureCtoMapForCtoNode(ctoNode) {
  if (!ctoNode || !ctoNode.hasAttribute("data-cto-node")) return;
  const body = ctoNode.nextElementSibling;
  if (!body || body.classList.contains("hidden")) return;
  const mapPanel = body.querySelector("[data-cto-map-panel]");
  if (!mapPanel || mapPanel.classList.contains("hidden")) return;
  const shell = body.querySelector("[data-cto-map-shell]");
  if (!shell) return;
  const status = mapPanel.dataset.mapReady;
  if (status === "done" || status === "nocords") return;
  if (status === "loading") return;
  const cto = (ctoNode.getAttribute("data-cto") || "").trim();
  if (!cto) return;

  const msg = mapPanel.querySelector(".rama-cto-map-msg");
  const canvas = mapPanel.querySelector(".rama-cto-map-canvas");
  if (!msg || !canvas) return;

  mapPanel.dataset.mapReady = "loading";
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
        mapPanel.dataset.mapReady = "nocords";
        return;
      }
      if (typeof window.L === "undefined") {
        msg.textContent = "No se pudo cargar el mapa (Leaflet).";
        canvas.hidden = true;
        mapPanel.dataset.mapReady = "nocords";
        return;
      }
      const lat = Number(data.lat);
      const lon = Number(data.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        msg.textContent = "Sin coordenadas para esta CTO";
        canvas.hidden = true;
        mapPanel.dataset.mapReady = "nocords";
        return;
      }
      msg.textContent = "";
      canvas.hidden = false;

      if (!mapPanel._leafletMap) {
        if (window.NocMapTiles && window.NocMapTiles.createLeafletMap) {
          const created = window.NocMapTiles.createLeafletMap(canvas, { lat, lon, zoom: 17, marker: true });
          if (!created) {
            msg.textContent = "No se pudo inicializar el mapa.";
            canvas.hidden = true;
            mapPanel.dataset.mapReady = "nocords";
            return;
          }
          mapPanel._leafletMap = created.map;
          shell._nocMapBasemap = created.basemap;
        } else {
          const mapOpts =
            window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
              ? window.NocLeafletMap.baseMapOptions()
              : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
          const map = window.L.map(canvas, mapOpts).setView([lat, lon], 17);
          window.L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
            attribution: "&copy; OpenStreetMap &copy; CARTO",
            maxZoom: 19,
          }).addTo(map);
          window.L.marker([lat, lon]).addTo(map);
          mapPanel._leafletMap = map;
          if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
            window.NocLeafletMap.attachScrollActivation(map, canvas);
          }
          if (window.NocMapFullscreen) {
            window.NocMapFullscreen.attachMapFullscreen(map, canvas);
          }
          if (window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
            window.NocMapTiles.refreshLeafletMapLayout(map);
          }
        }
      } else if (window.NocMapTiles && window.NocMapTiles.updateMapMarker) {
        window.NocMapTiles.updateMapMarker(mapPanel._leafletMap, lat, lon, 17);
      } else if (window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
        window.NocMapTiles.refreshLeafletMapLayout(mapPanel._leafletMap);
      }
      mapPanel.dataset.mapReady = "done";
      _ramaRefreshMapTiles(mapPanel._leafletMap, shell._nocMapBasemap);
    })
    .catch(() => {
      msg.textContent = "No se pudo obtener la ubicación.";
      canvas.hidden = true;
      delete mapPanel.dataset.mapReady;
    });
}

function ensureCtoAddressForCtoNode(ctoNode) {
  if (!ctoNode || !ctoNode.hasAttribute("data-cto-node")) return;
  const body = ctoNode.nextElementSibling;
  if (!body || body.classList.contains("hidden")) return;
  const shell = body.querySelector("[data-cto-map-shell]");
  const addrEl = body.querySelector("[data-cto-postal-address]");
  if (!shell || !addrEl) return;

  const status = shell.dataset.addrReady;
  if (status === "done" || status === "noaddr" || status === "loading") return;

  const cto = (ctoNode.getAttribute("data-cto") || "").trim();
  if (!cto) return;

  shell.dataset.addrReady = "loading";
  addrEl.innerHTML = '<span class="rama-cto-address__loading">Buscando dirección…</span>';

  fetch(_RAMA_CTO_ADDRESS_URL + "?cto=" + encodeURIComponent(cto))
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      if (!data || !data.ok || !data.address) {
        addrEl.textContent = "";
        shell.dataset.addrReady = "noaddr";
        return;
      }
      const addr = _escHtml(String(data.address || "").trim());
      addrEl.innerHTML =
        '<span class="rama-cto-address__label">Dirección</span>' +
        '<span class="rama-cto-address__value">' + addr + "</span>";
      shell.dataset.addrReady = "done";
    })
    .catch(() => {
      addrEl.textContent = "";
      delete shell.dataset.addrReady;
    });
}

function verMapaCto(btn) {
  if (!btn) return;
  const ctoNode = btn.closest("[data-cto-node]");
  if (!ctoNode) return;
  const body = ctoNode.nextElementSibling;
  if (!body) return;
  const panel = body.querySelector("[data-cto-map-panel]");
  if (!panel) return;

  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    btn.textContent = "Ver mapa";
    btn.setAttribute("aria-expanded", "false");
    _saveStateSoon();
    return;
  }

  const shell = body.querySelector("[data-cto-map-shell]");

  const openPanel = () => {
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    btn.textContent = "Ocultar mapa";
    btn.setAttribute("aria-expanded", "true");
    ensureCtoAddressForCtoNode(ctoNode);
    ensureCtoMapForCtoNode(ctoNode);
    _ramaRefreshMapTiles(panel._leafletMap, shell?._nocMapBasemap || panel._nocMapBasemap);
    _saveStateSoon();
  };

  if (body.classList.contains("hidden")) {
    body.classList.remove("hidden");
    setExpanded(ctoNode, true);
  }
  openPanel();
}

function _ramaRefreshMapTiles(map, basemapCtrl) {
  if (basemapCtrl && typeof basemapCtrl.redraw === "function") {
    basemapCtrl.redraw();
  } else if (map && window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
    window.NocMapTiles.refreshLeafletMapLayout(map);
    setTimeout(() => {
      if (map && window.NocMapTiles) window.NocMapTiles.refreshLeafletMapLayout(map);
    }, 120);
  }
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
    indent2.classList.remove("hidden");
    if (ramaRow) setExpanded(ramaRow, true);
    cargarInventarioRama(rama, card, detail).finally(() => {
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

  Promise.all([
    fetch(_RAMA_MAP_URL + "?rama=" + encodeURIComponent(rama)).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    fetch(_RAMA_CAMINO_GIS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ rama: rama }),
    })
      .then((r) => (r.ok ? r.json() : { ok: false, error: "Error HTTP GIS" }))
      .catch(() => ({ ok: false, error: "Error GIS" })),
  ])
    .then(([data, gis]) => {
      if (!data || !data.ok) {
        msg.textContent = (data && data.error) || "No se pudo cargar el mapa de la RAMA.";
        canvas.hidden = true;
        return;
      }
      const markers = Array.isArray(data.markers) ? data.markers : [];
      const sinCoord =
        data.ctos_sin_coordenadas != null ? Number(data.ctos_sin_coordenadas) : 0;
      const ctosTotal = data.ctos_total != null ? Number(data.ctos_total) : 0;
      const gj = gis && gis.ok && gis.geojson ? gis.geojson : null;
      const hasPath = !!(gj && Array.isArray(gj.features) && gj.features.length > 0);

      if (markers.length === 0 && !hasPath) {
        if (ctosTotal === 0) {
          msg.textContent = "No hay CTO en inventario para esta RAMA.";
        } else {
          msg.textContent = "Ninguna CTO de esta RAMA tiene coordenadas cargadas.";
        }
        if (gis && gis.error) msg.textContent += " " + gis.error;
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
        if (hasPath) foot += " · trazado ci_op visible";
        footer.textContent = foot + ".";
      }

      if (typeof window.L === "undefined") {
        msg.textContent = "No se pudo cargar el mapa (Leaflet).";
        canvas.hidden = true;
        return;
      }

      let map = panel._ramaLeafletMap;
      if (!map) {
        if (window.NocMapTiles && window.NocMapTiles.createLeafletMap) {
          const created = window.NocMapTiles.createLeafletMap(canvas, { marker: false, zoom: 11 });
          map = created ? created.map : null;
          if (created) panel._nocMapBasemap = created.basemap;
        }
        if (!map) {
          const mapOpts =
            window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
              ? window.NocLeafletMap.baseMapOptions()
              : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
          map = window.L.map(canvas, mapOpts);
          if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
            panel._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
          }
          if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
            window.NocLeafletMap.attachScrollActivation(map, canvas);
          }
          if (window.NocMapFullscreen) {
            window.NocMapFullscreen.attachMapFullscreen(map, canvas);
          }
        }
        panel._ramaLeafletMap = map;
      }

      if (panel._ramaMarkerLayer) {
        map.removeLayer(panel._ramaMarkerLayer);
        panel._ramaMarkerLayer = null;
      }
      if (panel._ramaPathLayer) {
        map.removeLayer(panel._ramaPathLayer);
        panel._ramaPathLayer = null;
      }

      if (hasPath) {
        try {
          panel._ramaPathLayer = window.L.geoJSON(gj, {
            style: function (_feature) {
              return {
                color: "#22c55e",
                weight: 6,
                opacity: 1,
                lineCap: "round",
                lineJoin: "round",
              };
            },
            filter: function (feature) {
              return !!(feature && feature.geometry);
            },
          }).addTo(map);
        } catch (_ePath) {
          panel._ramaPathLayer = null;
        }
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
      if (fg.getLayers().length > 0) {
        fg.addTo(map);
        panel._ramaMarkerLayer = fg;
      }

      requestAnimationFrame(() => {
        if (!_fitRamaMapToData(map, gj, markers)) {
          map.setView([-34.6, -58.38], 11);
        }
        _ramaRefreshMapTiles(map, panel._nocMapBasemap);
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
      next.classList.remove("hidden");
      setExpanded(el, true);
      cargarInventarioRama(rama, card, container).finally(() => {
        _saveStateSoon();
      });
      return;
    }
  }
  next.classList.toggle("hidden");
  setExpanded(el, willExpand);
  if (willExpand && el.hasAttribute("data-cto-node") && !isRamaRow) {
    ensureCtoAddressForCtoNode(el);
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
      ensureCtoAddressForCtoNode(ctoNode);
    }
  });
}

function _setVisibleRamaCount(visible) {
  const counter = document.getElementById("visibleCount");
  if (!counter) return;
  const nEl =
    counter.querySelector('[data-metric="n"]') ||
    counter.querySelector(".dashboard-metric-pill__n");
  if (nEl) {
    nEl.textContent = String(visible);
    counter.classList.remove("dashboard-metric-pill--pending");
  } else {
    counter.textContent = `${visible} RAMAs`;
  }
}

function aplicarFiltro() {
  const raw = (document.getElementById("q")?.value || "").trim();
  const q = raw.toLowerCase();
  const rows = document.querySelectorAll("[data-rama-card]");

  if (!q) {
    clearSearchHighlights();
    document.querySelectorAll(".principal-block").forEach((pb) => {
      pb.style.display = "";
    });
    rows.forEach((card) => {
      card.style.display = "";
      card.classList.remove("filter-match");
    });
    _setVisibleRamaCount(rows.length);
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

  _setVisibleRamaCount(visible);

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

const _np = () => window.NocPower;

/** Misma regla que consulta índice / ``clasificar_rx_dbm`` (-27 rojo, -25 amarillo). */
function _aplicarResaltadoFila(tr, rxValue) {
  if (!tr) return;
  tr.classList.remove(
    "consulta-fila-sem-rojo",
    "consulta-fila-sem-amarillo",
    "rx-warn",
    "rx-alert"
  );
  const cat = _np()?.clasificarRxDbm(rxValue);
  if (cat === "rojo") tr.classList.add("consulta-fila-sem-rojo");
  else if (cat === "amarillo") tr.classList.add("consulta-fila-sem-amarillo");
}

/** Reaplica semáforo en filas que ya tienen RX (p. ej. tras expandir CTO sin nueva consulta). */
function _sincronizarResaltadoPotenciasEn(root) {
  if (!root) return;
  root.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (_ramaFatSkipPotencias(tr)) return;
    const tdRx = tr.children[RAMA_COL_RX];
    if (!tdRx || tdRx.classList.contains("olt-txrx-cell--loading")) return;
    const txt = (tdRx.textContent || "").trim();
    if (!txt || txt === "-" || txt === "Cargando...") return;
    _aplicarResaltadoFila(tr, txt);
  });
}

function _hasPowerRama(v) {
  return _np() ? _np().hasPowerValue(v) : false;
}

function _formatPowerDbm(v) {
  return _np() ? _np().formatPowerDbm(v) : "-";
}

function _applyPotenciaEnFilaRama(tr, txVal, rxVal) {
  if (!tr || _ramaFatSkipPotencias(tr)) return;
  const tdTx = tr.children[RAMA_COL_TX];
  const tdRx = tr.children[RAMA_COL_RX];
  const np = _np();
  if (np) {
    np.finalizeTxRxLoadingCell(tdTx, txVal, tr);
    np.finalizeTxRxLoadingCell(tdRx, rxVal, tr);
  } else {
    [tdTx, tdRx].forEach((td, i) => {
      if (!td) return;
      td.classList.remove("olt-txrx-cell--loading");
      td.removeAttribute("aria-busy");
      td.removeAttribute("aria-label");
      const v = i === 0 ? txVal : rxVal;
      td.textContent = v != null && String(v).trim() !== "" ? String(v) : "-";
    });
  }
  if (tdRx) _aplicarResaltadoFila(tr, tdRx.textContent);
}

/** Consulta TX/RX en CTOs ya expandidas (restaurar estado, inventario recién pintado). */
function _ramaPotenciasParaCtosExpandidosEn(root) {
  if (!root) return;
  const card = root.matches && root.matches("[data-rama-card]")
    ? root
    : root.closest && root.closest("[data-rama-card]");
  if (card && card._skipAutoPotenciasCto) return;
  root.querySelectorAll("[data-cto-node][aria-expanded='true']").forEach((ctoNode) => {
    const ctoBody = ctoNode.nextElementSibling;
    if (!ctoBody || ctoBody.classList.contains("hidden")) return;
    _autoConsultarCtoPotenciasAlExpandir(ctoNode);
  });
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
  if (st === "FREE" || st === "RESERVED") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
  } else {
    txCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    rxCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
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
          <button type="button" class="btn-mini pot-cto" data-pot-cto="${encodeURIComponent(cto)}">Consultar RX</button>
          <button
            type="button"
            class="btn-mini pot-cto"
            onclick="event.stopPropagation(); verMapaCto(this);"
            title="Mostrar mapa de la CTO"
            aria-expanded="false"
          >Ver mapa</button>
        </span>
      </div>
      <div class="hidden indent3">
        <div class="rama-cto-map-shell" data-cto-map-shell data-cto="${_escHtml(cto)}">
          <p class="hint rama-cto-address" data-cto-postal-address aria-live="polite"></p>
        </div>
        <div class="rama-cto-map-panel hidden" data-cto-map-panel aria-hidden="true">
          <p class="hint rama-cto-map-msg" aria-live="polite"></p>
          <div class="rama-cto-map-canvas" hidden></div>
        </div>
        <div class="table-wrap">
          <table>
            <tr><th>OUT</th><th>AID</th><th>Operador</th><th>Sitio</th><th>RAMA</th><th>ONT</th><th>Status</th><th>TX (dBm)</th><th>RX (dBm)</th></tr>
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
  _ramaPotenciasParaCtosExpandidosEn(container.closest("[data-rama-card]") || container);
}

function cargarInventarioRama(rama, card, container) {
  const ramaKey = String(rama || "").trim().toUpperCase();
  if (!ramaKey) return Promise.resolve();
  if (_ramaInventarioCargado[ramaKey]) return Promise.resolve();
  if (_ramaInventarioCargando[ramaKey]) return _ramaInventarioCargando[ramaKey];

  container.innerHTML = _ramaInventarioLoadingHtml();
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

function _expandAllCtosInRamaCard(card, autoPotencias) {
  if (!card) return;
  const fetchPotencias = autoPotencias !== false;
  card.querySelectorAll("[data-cto-node]").forEach((ctoNode) => {
    const ctoBody = ctoNode.nextElementSibling;
    if (!ctoBody) return;
    ctoBody.classList.remove("hidden");
    setExpanded(ctoNode, true);
    ensureCtoAddressForCtoNode(ctoNode);
    if (fetchPotencias) {
      _autoConsultarCtoPotenciasAlExpandir(ctoNode);
    }
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
      ensureCtoAddressForCtoNode(ctoNode);
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

function _ramaFinalizeTxRxPendientes(card) {
  if (!card) return;
  card.querySelectorAll("tr[data-aid]").forEach((tr) => {
    const tdTx = tr.children[RAMA_COL_TX];
    const tdRx = tr.children[RAMA_COL_RX];
    const loading =
      (tdTx && tdTx.classList.contains("olt-txrx-cell--loading")) ||
      (tdRx && tdRx.classList.contains("olt-txrx-cell--loading"));
    if (loading) _applyPotenciaEnFilaRama(tr, null, null);
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
    if (!tr.children[RAMA_COL_TX] || !tr.children[RAMA_COL_RX]) return;
    if (data[cto] && data[cto][aid]) {
      _applyPotenciaEnFilaRama(tr, data[cto][aid].TX, data[cto][aid].RX);
    } else if (_np() && _np().filaTieneAidConsulta(tr)) {
      _applyPotenciaEnFilaRama(tr, null, null);
    }
  });
  _sincronizarResaltadoPotenciasEn(root);
}

function _setRamaPotButtonLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    if (!btn.dataset.potLabel) btn.dataset.potLabel = (btn.textContent || "").trim() || "Consultar RX";
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
    btn.textContent = btn.dataset.potLabel || "Consultar RX";
  }
}

function _autoConsultarCtoPotenciasAlExpandir(ctoNode) {
  const ctoBody = ctoNode.nextElementSibling;
  if (!ctoBody) return;
  const card = ctoNode.closest("[data-rama-card]");
  if (card && card._skipAutoPotenciasCto) return;
  if (!_ctoBodyTieneFilasPendientesPotencias(ctoBody)) {
    _sincronizarResaltadoPotenciasEn(ctoBody);
    return;
  }
  const cto = (ctoNode.getAttribute("data-cto") || "").trim();
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
      const seen = new Set();
      rows.forEach((rec) => {
        const aid = String(rec.AID || "");
        if (!aid) return;
        const tr = _findTrByAidInCtoBody(ctoBody, aid);
        if (!tr || _ramaFatSkipPotencias(tr)) return;
        seen.add(aid);
        _applyPotenciaEnFilaRama(tr, rec.TX, rec.RX);
      });
      ctoBody.querySelectorAll("tr[data-aid]").forEach((tr) => {
        if (_ramaFatSkipPotencias(tr)) return;
        const aid = String(tr.getAttribute("data-aid") || "");
        if (!aid || seen.has(aid)) return;
        if (_np() && _np().filaTieneAidConsulta(tr)) {
          _applyPotenciaEnFilaRama(tr, null, null);
        }
      });
      _saveStateSoon();
      _sincronizarResaltadoPotenciasEn(ctoBody);
      if (!silentToast) {
        toast(`Potencias actualizadas CTO: ${cto}`);
      }
    })
    .catch(() => {
      toast(`Error consultando potencias CTO: ${cto}`);
    })
    .finally(() => {
      _ramaFinalizeTxRxPendientes(ctoBody);
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
      return Promise.resolve();
    }

    _setRamaPotButtonLoading(btn, true);
    if (card) {
      _setRamaCardTxRxCellsLoading(card);
    }

    return fetch("/dashboard/rama/consultar", {
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
          _ramaFinalizeTxRxPendientes(card);
        }
        _setRamaPotButtonLoading(btn, false);
      });
  };

  _expandRamaCardAndEnsureInventory(card, rama).then(() => {
    if (card) card._skipAutoPotenciasCto = true;
    _expandAllCtosInRamaCard(card, false);
    _saveStateSoon();
    return ejecutarConsulta();
  }).finally(() => {
    if (card) delete card._skipAutoPotenciasCto;
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
      if (_filtroRamaTimer) clearTimeout(_filtroRamaTimer);
      _filtroRamaTimer = setTimeout(aplicarFiltro, 220);
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
