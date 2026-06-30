/**
 * NOC: atajos de foco en el campo de búsqueda (/ y Ctrl+K; Esc limpia si está en el input).
 */
(function () {
  let _opts = null;
  let _keysBound = false;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function bindKeys() {
    if (_keysBound) return;
    _keysBound = true;
    document.addEventListener(
      "keydown",
      function (e) {
        const t = e.target;
        const inField = t && (t.matches("input, textarea, select") || t.isContentEditable);
        if ((e.key === "/" || (e.ctrlKey && e.key.toLowerCase() === "k")) && !inField) {
          e.preventDefault();
          const inp = _opts && _opts.searchSelector ? $(_opts.searchSelector) : null;
          if (inp) inp.focus();
          return;
        }
        if (e.key === "Escape" && inField && _opts && _opts.searchSelector && t.matches(_opts.searchSelector)) {
          if (_opts.onClear) {
            e.preventDefault();
            _opts.onClear();
          }
        }
      },
      true
    );
  }

  window.initNocPage = function (options) {
    _opts = options || {};
    bindKeys();
  };

  function createNocPageStateStore(storageKey, opts) {
    const key = String(storageKey || "").trim();
    const options = opts || {};
    let timer = null;

    function _saveNow(buildPayload) {
      if (!key || typeof buildPayload !== "function") return;
      try {
        const payload = buildPayload();
        if (!payload || typeof payload !== "object") return;
        sessionStorage.setItem(key, JSON.stringify(payload));
      } catch (_err) {
        // Best-effort cache only.
      }
    }

    function saveSoon(buildPayload) {
      const waitMs = Number(options.debounceMs || 120);
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        _saveNow(buildPayload);
      }, waitMs > 0 ? waitMs : 120);
    }

    function read(normalizeFn) {
      if (!key) return null;
      try {
        const raw = sessionStorage.getItem(key);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (typeof normalizeFn === "function") return normalizeFn(parsed);
        return parsed;
      } catch (_err) {
        try {
          sessionStorage.removeItem(key);
        } catch (_innerErr) {}
        return null;
      }
    }

    function restoreScroll(scrollY) {
      const y = Number(scrollY);
      if (!Number.isFinite(y) || y <= 0) return;
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          window.scrollTo({ top: y, behavior: "auto" });
        });
      });
    }

    return {
      save: _saveNow,
      saveSoon: saveSoon,
      read: read,
      restoreScroll: restoreScroll,
    };
  }

  window.createNocPageStateStore = createNocPageStateStore;

  let _lastPointer = null;
  const TOAST_POINTER_MAX_MS = 4000;
  const TOAST_VARIANTS = ["success", "error", "info"];
  const TOAST_ICONS = { success: "✓", error: "!", info: "ℹ" };
  const _toastTimers = new Map();
  const _wiredToasts = new WeakSet();

  document.addEventListener(
    "pointerdown",
    function (e) {
      _lastPointer = { x: e.clientX, y: e.clientY, t: Date.now() };
    },
    true
  );

  function _toastEl(elOrId) {
    if (!elOrId) return null;
    if (typeof elOrId === "string") return document.getElementById(elOrId);
    return elOrId;
  }

  function _toastAnchorClass() {
    return "noc-toast--at-pointer";
  }

  function resetToastAnchor(el) {
    if (!el) return;
    el.classList.remove("noc-toast--at-pointer", "toast--at-pointer", "historico-toast--at-pointer");
    el.style.left = "";
    el.style.top = "";
    el.style.right = "";
    el.style.bottom = "";
  }

  function positionToastNearPointer(el, opts) {
    if (!el) return false;
    opts = opts || {};
    resetToastAnchor(el);
    if (opts.atPointer !== true) return false;
    const p =
      _lastPointer && Date.now() - _lastPointer.t <= TOAST_POINTER_MAX_MS ? _lastPointer : null;
    if (!p) return false;

    const anchorClass = _toastAnchorClass();
    el.classList.add(anchorClass);
    el.style.right = "auto";
    el.style.bottom = "auto";

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (!el.classList.contains(anchorClass)) return;
        const margin = 12;
        const offsetY = 10;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const w = el.offsetWidth || 280;
        const h = el.offsetHeight || 40;
        let left = p.x + margin;
        let top = p.y + offsetY;
        if (left + w > vw - 8) left = Math.max(8, p.x - w - margin);
        if (top + h > vh - 8) top = Math.max(8, p.y - h - margin);
        el.style.left = Math.round(left) + "px";
        el.style.top = Math.round(top) + "px";
      });
    });
    return true;
  }

  function _toastTextEl(el) {
    return el.querySelector(".noc-toast__text") || el.querySelector(".altiplano-consulta-toast__text");
  }

  function _toastIconEl(el) {
    return el.querySelector(".noc-toast__icon") || el.querySelector(".altiplano-consulta-toast__icon");
  }

  function _toastCloseEl(el) {
    return el.querySelector(".noc-toast__close") || el.querySelector(".altiplano-consulta-toast__close");
  }

  function setToastDismissible(el, dismissible) {
    if (!el) return;
    const locked = dismissible === false;
    el.classList.toggle("noc-toast--locked", locked);
    el.setAttribute("aria-live", locked ? "assertive" : "polite");
    const closeBtn = _toastCloseEl(el);
    if (closeBtn) {
      closeBtn.hidden = locked;
      closeBtn.disabled = locked;
      closeBtn.setAttribute("aria-hidden", locked ? "true" : "false");
    }
  }

  function ensureToastStructure(el) {
    if (!el) return null;
    if (_toastTextEl(el)) return el;
    const msg = el.textContent || "";
    el.textContent = "";
    el.classList.add("noc-toast", "noc-toast--success");
    el.innerHTML =
      '<span class="noc-toast__icon" aria-hidden="true">✓</span>' +
      '<p class="noc-toast__text"></p>' +
      '<button type="button" class="noc-toast__close" aria-label="Cerrar">×</button>';
    const textEl = _toastTextEl(el);
    if (textEl) textEl.textContent = msg;
    wireToast(el);
    return el;
  }

  function wireToast(elOrId) {
    const el = ensureToastStructure(_toastEl(elOrId));
    if (!el || _wiredToasts.has(el)) return el;
    const closeBtn = _toastCloseEl(el);
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        if (el.classList.contains("noc-toast--locked")) return;
        hideToast(el);
      });
    }
    _wiredToasts.add(el);
    return el;
  }

  function hideToast(elOrId, opts) {
    opts = opts || {};
    const el = _toastEl(elOrId);
    if (!el) return;
    if (el.classList.contains("noc-toast--locked") && opts.force !== true) return;
    const key = el.id || el;
    el.classList.remove("is-visible", "show", "historico-toast--show");
    if (_toastTimers.has(key)) {
      clearTimeout(_toastTimers.get(key));
      _toastTimers.delete(key);
    }
    window.setTimeout(function () {
      if (!el.classList.contains("is-visible") && !el.classList.contains("show")) {
        el.hidden = true;
      }
    }, 220);
    resetToastAnchor(el);
  }

  function showToast(elOrId, message, opts) {
    opts = opts || {};
    let el = _toastEl(elOrId);
    if (!el && opts.create) {
      el = document.createElement("div");
      el.id = opts.id || "noc-toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.hidden = true;
      document.body.appendChild(el);
    }
    el = wireToast(el);
    if (!el) return;

    const variant = TOAST_VARIANTS.indexOf(opts.variant) >= 0 ? opts.variant : "success";
    const textEl = _toastTextEl(el);
    const iconEl = _toastIconEl(el);
    if (textEl) textEl.textContent = message != null ? String(message) : "";
    if (iconEl) iconEl.textContent = TOAST_ICONS[variant] || TOAST_ICONS.success;

    el.classList.remove("noc-toast--success", "noc-toast--error", "noc-toast--info");
    el.classList.remove(
      "altiplano-consulta-toast--success",
      "altiplano-consulta-toast--error"
    );
    el.classList.add("noc-toast", "noc-toast--" + variant);
    if (el.classList.contains("altiplano-consulta-toast")) {
      el.classList.add("altiplano-consulta-toast--" + variant);
    }

    setToastDismissible(el, opts.dismissible !== false);

    resetToastAnchor(el);
    positionToastNearPointer(el, opts);

    el.hidden = false;
    const keepVisible = opts.keepVisible === true && el.classList.contains("is-visible");
    if (!keepVisible) {
      el.classList.remove("show", "historico-toast--show");
      requestAnimationFrame(function () {
        el.classList.add("is-visible");
      });
    } else {
      el.classList.add("is-visible");
    }

    const key = el.id || el;
    if (_toastTimers.has(key)) {
      clearTimeout(_toastTimers.get(key));
      _toastTimers.delete(key);
    }
    const ms = opts.durationMs != null ? Number(opts.durationMs) : 2200;
    if (ms > 0) {
      _toastTimers.set(
        key,
        window.setTimeout(function () {
          hideToast(el);
        }, ms)
      );
    }
    return el;
  }

  function wireAllToasts() {
    document.querySelectorAll(".noc-toast, .toast, .altiplano-consulta-toast").forEach(function (el) {
      wireToast(el);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireAllToasts);
  } else {
    wireAllToasts();
  }

  window.NocToast = {
    positionNearPointer: positionToastNearPointer,
    resetAnchor: resetToastAnchor,
    ensureStructure: ensureToastStructure,
    wire: wireToast,
    wireAll: wireAllToasts,
    show: showToast,
    hide: hideToast,
  };

  /** RX / TX Altiplano: misma regla que ``clasificar_rx_dbm`` en ``services/domain.py``. */
  function parseRxDbm(rx) {
    if (rx === null || rx === undefined) return null;
    if (typeof rx === "number") {
      return Number.isFinite(rx) ? rx : null;
    }
    var s = String(rx).trim();
    if (!s || s === "-" || s === "⏳") return null;
    s = s
      .replace(/\u2212|\u2013|\u2014/g, "-")
      .replace(",", ".")
      .replace(/dbm$/i, "")
      .trim();
    var v = parseFloat(s);
    return Number.isFinite(v) ? v : null;
  }

  function clasificarRxDbm(rx) {
    var v = parseRxDbm(rx);
    if (v === null) return null;
    if (v < -27) return "rojo";
    if (v <= -25) return "amarillo";
    return "verde";
  }

  function formatPowerDbm(v) {
    if (v === null || v === undefined) return "-";
    var raw = String(v).trim();
    if (!raw || raw === "-" || raw === "⏳") return raw || "-";
    if (/dbm$/i.test(raw)) return raw;
    return raw + " dBm";
  }

  function hasPowerValue(v) {
    return !(
      v === null ||
      v === undefined ||
      String(v).trim() === "" ||
      String(v).trim() === "-"
    );
  }

  function filaTieneAidConsulta(tr) {
    if (!tr) return false;
    const st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
    if (st === "FREE" || st === "RESERVED") return false;
    const aid = (tr.getAttribute("data-aid") || "").trim();
    if (!aid || aid.startsWith("nf-")) return false;
    return true;
  }

  /** Quita spinner de carga y pinta dBm o DOWN (dashboards RAMA / OLT / consulta). */
  function finalizeTxRxLoadingCell(td, rawValue, tr) {
    if (!td) return;
    td.classList.remove("olt-txrx-cell--loading");
    td.removeAttribute("aria-busy");
    td.removeAttribute("aria-label");
    applyPowerDbmCell(td, rawValue, filaTieneAidConsulta(tr));
  }

  /** Celda TX/RX en consulta CTO: valor en dBm o ``DOWN`` si hay abonado sin lectura. */
  function applyPowerDbmCell(el, v, hasSubscriber) {
    if (!el) return;
    el.classList.remove(
      "loading",
      "status-down",
      "status-up",
      "consulta-potencia-loading",
      "olt-txrx-cell--loading"
    );
    if (!hasSubscriber) {
      el.textContent = formatPowerDbm(v);
      if (hasPowerValue(v)) el.classList.add("status-up");
      return;
    }
    if (hasPowerValue(v)) {
      el.textContent = formatPowerDbm(v);
      el.classList.add("status-up");
      return;
    }
    el.textContent = "DOWN";
    el.classList.add("status-down");
  }

  /** Tono fila histórico potencias: ``bad`` / ``warn`` / ``ok`` / ``""``. */
  function rxHistoricoTone(db) {
    var cat = clasificarRxDbm(db);
    if (cat === "rojo") return "bad";
    if (cat === "amarillo") return "warn";
    if (cat === "verde") return "ok";
    return "";
  }

  function worstRxHistoricoTone(v1, v2) {
    var nums = [];
    if (v1 !== null && v1 !== undefined && Number.isFinite(Number(v1))) nums.push(Number(v1));
    if (v2 !== null && v2 !== undefined && Number.isFinite(Number(v2))) nums.push(Number(v2));
    if (!nums.length) return "";
    return rxHistoricoTone(Math.min.apply(null, nums));
  }

  window.NocPower = {
    parseRxDbm: parseRxDbm,
    clasificarRxDbm: clasificarRxDbm,
    formatPowerDbm: formatPowerDbm,
    hasPowerValue: hasPowerValue,
    applyPowerDbmCell: applyPowerDbmCell,
    filaTieneAidConsulta: filaTieneAidConsulta,
    finalizeTxRxLoadingCell: finalizeTxRxLoadingCell,
    rxHistoricoTone: rxHistoricoTone,
    worstRxHistoricoTone: worstRxHistoricoTone,
  };

  var CTO_TOOLTIP_BIND_OPTS = {
    direction: "top",
    opacity: 0.96,
    className: "camino-popup-cto camino-cto-hover-tip",
    interactive: true,
    offset: [0, -10],
  };

  function nocEscHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function coordTextFromLatLon(lat, lon) {
    var latN = Number(lat);
    var lonN = Number(lon);
    if (!Number.isFinite(latN) || !Number.isFinite(lonN)) return "";
    return latN.toFixed(6) + ", " + lonN.toFixed(6);
  }

  function ctoPopupHtml(cto, lat, lon, addr, opts) {
    opts = opts || {};
    var coordText = coordTextFromLatLon(lat, lon);
    var showAddrLoading = !!opts.showAddrLoading;
    var mapsLink = opts.mapsLink ? mapsLinkHtml(lat, lon, nocEscHtml) : "";
    return (
      '<div class="camino-popup-cto">' +
      '<div class="camino-popup-cto__id"><strong>' +
      nocEscHtml(cto || "") +
      "</strong></div>" +
      '<div class="camino-popup-cto__addr" data-rama-popup-addr>' +
      (addr
        ? '<span class="camino-popup-addr">' + nocEscHtml(addr) + "</span>"
        : showAddrLoading
        ? '<span class="muted">Buscando dirección…</span>'
        : '<span class="muted">Sin dirección postal</span>') +
      "</div>" +
      (coordText
        ? '<div class="camino-popup-cto__coords mono" title="Latitud, Longitud">' +
          nocEscHtml(coordText) +
          "</div>" +
          mapsLink +
          '<div class="camino-popup-cto__copy muted">Click en la CTO para copiar coordenadas</div>'
        : "") +
      "</div>"
    );
  }

  function buildCtoCopyOpts(opts) {
    opts = opts || {};
    return Object.assign(
      {
        toastMsg: "Coordenadas copiadas al portapapeles",
        toastId: opts.toastId || "toast",
        durationMs: 1600,
      },
      opts.map ? { map: opts.map } : {},
      opts.copyOpts || {},
      opts
    );
  }

  function wireCtoAddressPrefetch(mk, url, renderTooltip) {
    if (!mk || !url || typeof renderTooltip !== "function") return;
    mk._nocAddrResolved = false;
    mk.on("mouseover", function () {
      if (mk._nocAddrResolved) return;
      mk._nocAddrResolved = true;
      fetch(url)
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          var addr = data && data.ok && data.address ? String(data.address).trim() : "";
          mk.setTooltipContent(renderTooltip(addr));
        })
        .catch(function () {
          mk.setTooltipContent(renderTooltip(""));
        });
    });
  }

  function ensureMapCtoWiring(map) {
    ensureMapCoordCopy(map);
    ensureMapCtoTooltipDismiss(map);
  }

  function googleMapsSearchUrl(lat, lon) {
    var latN = Number(lat);
    var lonN = Number(lon);
    if (!Number.isFinite(latN) || !Number.isFinite(lonN)) return "";
    return (
      "https://www.google.com/maps/search/?api=1&query=" +
      encodeURIComponent(String(latN) + "," + String(lonN))
    );
  }

  function mapsLinkHtml(lat, lon, escFn) {
    var url = googleMapsSearchUrl(lat, lon);
    if (!url) return "";
    var esc =
      typeof escFn === "function"
        ? escFn
        : function (v) {
            return String(v || "");
          };
    return (
      '<div class="camino-popup-cto__maps">' +
      '<a href="' +
      esc(url) +
      '" target="_blank" rel="noopener noreferrer" class="camino-popup-cto__maps-link" onclick="event.stopPropagation();">Abrir en Maps</a>' +
      "</div>"
    );
  }

  var _lastMapCoordCopy = { text: "", at: 0 };

  function copyMapCoords(text, opts) {
    if (!text) return;
    opts = opts || {};
    var now = Date.now();
    if (!opts.fromClick) {
      if (text === _lastMapCoordCopy.text && now - _lastMapCoordCopy.at < 450) return;
    }
    _lastMapCoordCopy = { text: text, at: now };
    var copyOpts = Object.assign(
      {
        toastMsg: "Coordenadas copiadas al portapapeles",
        failMsg: "No se pudo copiar",
        preferSync: !!opts.fromClick,
        durationMs: 1600,
      },
      opts || {}
    );
    if (window.NocClipboard && window.NocClipboard.copyText) {
      window.NocClipboard.copyText(text, copyOpts);
      return;
    }
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "readonly");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      if (document.execCommand("copy")) {
        notifyMapCoordCopy(copyOpts.toastMsg, copyOpts);
      }
      document.body.removeChild(ta);
    } catch (_fb) {}
  }

  function eventEl(node) {
    var el = node;
    while (el && el.nodeType === 3) {
      el = el.parentElement;
    }
    return el || null;
  }

  function elClosest(node, sel) {
    var el = eventEl(node);
    return el && el.closest ? el.closest(sel) : null;
  }

  function markerHoverStyle(base) {
    base = base || {};
    return {
      radius: Math.min((base.radius || 9) + 5, 22),
      fillColor: base.fillColor,
      color: base.color,
      weight: Math.min((base.weight || 2) + 2, 5),
      opacity: base.opacity,
      fillOpacity: Math.min((base.fillOpacity != null ? base.fillOpacity : 0.95) + 0.04, 1),
    };
  }

  function wirePopupCopySurface(popupEl, coordText, opts) {
    if (!popupEl || !coordText) return;
    if (popupEl._nocPopupCopyHandler) {
      popupEl.removeEventListener("click", popupEl._nocPopupCopyHandler);
      popupEl._nocPopupCopyHandler = null;
    }
    popupEl._nocPopupCopyHandler = function (ev) {
      if (elClosest(ev.target, "a")) return;
      if (elClosest(ev.target, ".leaflet-popup-close-button")) return;
      copyMapCoords(coordText, opts);
    };
    popupEl.addEventListener("click", popupEl._nocPopupCopyHandler);
  }

  function rewireMarkerPopupCopy(mk, coordText, opts) {
    if (!mk) return;
    var popup = mk.getPopup ? mk.getPopup() : null;
    var el = popup && popup.getElement ? popup.getElement() : null;
    if (el) wirePopupCopySurface(el, coordText, opts);
  }

  function bindMarkerPopupCopy(mk, coordText, opts) {
    opts = opts || {};
    mk._nocCoordText = coordText;
    mk._nocPopupCopyOpts = opts.copyOpts || {};
  }

  function ensureMapCoordCopy(map) {
    if (!map || map._nocCoordCopyWired) return;
    map._nocCoordCopyWired = true;
    map.on("click", function (e) {
      var layer = e.layer;
      if (!layer || !layer._nocCoordText) return;
      var orig = e.originalEvent;
      if (elClosest(orig && orig.target, "a")) return;
      if (elClosest(orig && orig.target, ".leaflet-popup-close-button")) return;
      var layerOpts = Object.assign({ map: map }, layer._nocPopupCopyOpts || {});
      copyMapCoords(layer._nocCoordText, layerOpts);
    });
    map.on("popupopen", function (e) {
      var popup = e.popup;
      var src = popup && popup._source;
      var coordText = src && src._nocCoordText;
      if (!coordText || !popup.getElement) return;
      var popupOpts = Object.assign({ map: map }, (src && src._nocPopupCopyOpts) || {});
      wirePopupCopySurface(popup.getElement(), coordText, popupOpts);
    });
  }

  function patchCtoTooltipCloseGuard(mk) {
    if (!mk || mk._nocTooltipClosePatched) return;
    mk._nocTooltipClosePatched = true;
    mk._nocCloseTooltipOrig = mk.closeTooltip;
    mk.closeTooltip = function () {
      if (mk._nocTooltipPinned) {
        return mk;
      }
      return mk._nocCloseTooltipOrig.call(mk);
    };
  }

  function patchCtoTooltipInstanceCloseGuard(mk) {
    var tip = mk && mk.getTooltip ? mk.getTooltip() : null;
    if (!tip || tip._nocClosePatched) return;
    tip._nocClosePatched = true;
    tip._nocCloseOrig = tip.close;
    tip.close = function () {
      if (mk._nocTooltipPinned) {
        return tip;
      }
      return tip._nocCloseOrig.call(tip);
    };
  }

  function disableCtoTooltipHoverOpen(mk) {
    if (!mk || mk._nocTooltipHoverDisabled) return;
    mk._nocTooltipHoverDisabled = true;
    if (mk._initTooltipInteractions) {
      mk._initTooltipInteractions(true);
      return;
    }
    if (typeof mk._openTooltip === "function") {
      mk.off("mouseover", mk._openTooltip, mk);
      mk.off("click", mk._openTooltip, mk);
    }
    if (typeof mk.closeTooltip === "function") {
      mk.off("mouseout", mk.closeTooltip, mk);
    }
    if (typeof mk._moveTooltip === "function") {
      mk.off("mousemove", mk._moveTooltip, mk);
    }
  }

  function reinitCtoTooltipPinnedInteractions(mk) {
    if (!mk || !mk._tooltip) return;
    mk._tooltip.options.permanent = true;
    if (mk._initTooltipInteractions) {
      mk._initTooltipInteractions(true);
      mk._initTooltipInteractions(false);
    }
  }

  function dismissCtoTooltip(mk) {
    if (!mk) return;
    mk._nocTooltipPinned = false;
    var tip = mk.getTooltip ? mk.getTooltip() : null;
    if (tip) {
      tip.options.permanent = false;
      if (tip._nocCloseOrig) tip.close = tip._nocCloseOrig;
      tip._nocClosePatched = false;
    }
    if (mk._initTooltipInteractions) {
      mk._initTooltipInteractions(true);
    }
    mk._nocTooltipHoverDisabled = true;
    if (mk._nocCloseTooltipOrig) {
      mk._nocCloseTooltipOrig.call(mk);
    }
  }

  function ensureMapCtoTooltipDismiss(map) {
    if (!map || map._nocCtoTooltipDismissWired) return;
    map._nocCtoTooltipDismissWired = true;
    map.on("click", function (e) {
      var active = map._nocActiveCtoTooltipMarker;
      if (!active || !active._nocTooltipPinned) return;
      var target = e.originalEvent && e.originalEvent.target;
      if (elClosest(target, ".leaflet-tooltip")) return;
      if (elClosest(target, ".leaflet-interactive")) return;
      dismissCtoTooltip(active);
      map._nocActiveCtoTooltipMarker = null;
    });
  }

  function pinAndOpenCtoTooltip(mk, ev) {
    if (!mk || !mk.openTooltip) return;
    patchCtoTooltipCloseGuard(mk);
    var map = mk._map;
    if (map) {
      ensureMapCtoTooltipDismiss(map);
      var prev = map._nocActiveCtoTooltipMarker;
      if (prev && prev !== mk) {
        dismissCtoTooltip(prev);
      }
      map._nocActiveCtoTooltipMarker = mk;
    }
    mk._nocTooltipPinned = true;
    var ll = (ev && ev.latlng) || (mk.getLatLng ? mk.getLatLng() : null);
    try {
      if (mk._tooltip) {
        mk._tooltip._source = mk;
      }
      reinitCtoTooltipPinnedInteractions(mk);
      patchCtoTooltipInstanceCloseGuard(mk);
      mk.openTooltip(ll || undefined);
    } catch (_pin) {}
  }

  function notifyMapCoordCopy(msg, opts) {
    opts = Object.assign({ durationMs: 1600 }, opts || {});
    if (
      window.NocMapFullscreen &&
      window.NocMapFullscreen.showActiveToast &&
      window.NocMapFullscreen.showActiveToast(msg, opts)
    ) {
      return;
    }
    if (opts.toastId && window.NocToast) {
      window.NocToast.show(opts.toastId, msg, { durationMs: opts.durationMs });
    }
  }

  function onCtoMarkerActivate(mk, ev, coordText, opts) {
    if (!mk || !coordText) return;
    opts = opts || {};
    if (window.L && window.L.DomEvent && ev) {
      window.L.DomEvent.stopPropagation(ev);
      if (ev.originalEvent) {
        window.L.DomEvent.preventDefault(ev);
      }
    }
    var domEv = (ev && ev.originalEvent) || ev;
    if (domEv && domEv.stopPropagation) domEv.stopPropagation();
    pinAndOpenCtoTooltip(mk, ev);
    if (elClosest(domEv && domEv.target, "a")) return;
    var clickOpts = Object.assign({ fromClick: true, preferSync: true }, opts);
    if (!clickOpts.map && mk._map) clickOpts.map = mk._map;
    copyMapCoords(coordText, clickOpts);
  }

  function wireCtoTooltipCopySurface(mk, tooltipEl, coordText, copyOpts) {
    if (!mk || !tooltipEl || !coordText) return;
    if (tooltipEl._nocTipCopyHandler) {
      tooltipEl.removeEventListener("click", tooltipEl._nocTipCopyHandler);
      tooltipEl._nocTipCopyHandler = null;
    }
    tooltipEl._nocTipCopyHandler = function (ev) {
      ev.stopPropagation();
      if (elClosest(ev.target, "a")) return;
      onCtoMarkerActivate(mk, ev, coordText, copyOpts);
    };
    tooltipEl.addEventListener("click", tooltipEl._nocTipCopyHandler);
  }

  function wireCtoMarkerCopy(cm, coordText, copyOpts) {
    if (!coordText) return;
    cm._nocCoordText = coordText;
    cm._nocPopupCopyOpts = copyOpts || {};
    cm.on("add", function () {
      if (cm._map) ensureMapCoordCopy(cm._map);
    });
    if (cm._map) ensureMapCoordCopy(cm._map);
  }

  function wireCtoTooltipMarker(mk, tooltipHtml, coordText, opts, styleHooks) {
    opts = opts || {};
    styleHooks = styleHooks || {};
    var copyOpts = buildCtoCopyOpts(opts);
    mk.bindTooltip(tooltipHtml, CTO_TOOLTIP_BIND_OPTS);
    disableCtoTooltipHoverOpen(mk);
    mk._nocCtoTooltipWired = true;
    mk.on("add", function () {
      if (mk._map) ensureMapCtoWiring(mk._map);
    });
    if (mk._map) ensureMapCtoWiring(mk._map);
    if (opts.openTooltip) {
      window.setTimeout(function () {
        try {
          mk.openTooltip();
        } catch (_ot) {}
      }, 0);
    }
    if (typeof styleHooks.onMouseover === "function") {
      mk.on("mouseover", styleHooks.onMouseover);
    }
    if (typeof styleHooks.onMouseout === "function") {
      mk.on("mouseout", styleHooks.onMouseout);
    }
    mk.on("tooltipopen", function () {
      patchCtoTooltipInstanceCloseGuard(mk);
      var tip = mk.getTooltip ? mk.getTooltip() : null;
      var el = tip && tip.getElement ? tip.getElement() : null;
      var tipCopyOpts = Object.assign({}, copyOpts);
      if (!tipCopyOpts.map && mk._map) tipCopyOpts.map = mk._map;
      wireCtoTooltipCopySurface(mk, el, coordText, tipCopyOpts);
    });
    mk.on("click", function (ev) {
      onCtoMarkerActivate(mk, ev, coordText, copyOpts);
    });
  }

  function wireCtoCircleMarker(cm, tooltipHtml, styleBase, coordText, opts) {
    opts = opts || {};
    var base = {};
    Object.keys(styleBase || {}).forEach(function (k) {
      base[k] = styleBase[k];
    });
    cm._nocCtoBaseOpts = base;
    cm._nocCtoHoverOpts = markerHoverStyle(base);
    wireCtoTooltipMarker(cm, tooltipHtml, coordText, opts, {
      onMouseover: function () {
        cm.setStyle(cm._nocCtoHoverOpts);
        try {
          cm.bringToFront();
        } catch (_bf) {}
      },
      onMouseout: function () {
        cm.setStyle(cm._nocCtoBaseOpts);
      },
    });
  }

  function wireCtoPointMarker(mk, tooltipHtml, coordText, opts) {
    wireCtoTooltipMarker(mk, tooltipHtml, coordText, opts || {}, {});
  }

  window.NocMaps = {
    escHtml: nocEscHtml,
    googleMapsSearchUrl: googleMapsSearchUrl,
    mapsLinkHtml: mapsLinkHtml,
    coordTextFromLatLon: coordTextFromLatLon,
    ctoPopupHtml: ctoPopupHtml,
    copyMapCoords: copyMapCoords,
    markerHoverStyle: markerHoverStyle,
    ensureMapCoordCopy: ensureMapCoordCopy,
    ensureMapCtoWiring: ensureMapCtoWiring,
    wireCtoAddressPrefetch: wireCtoAddressPrefetch,
    wireCtoCircleMarker: wireCtoCircleMarker,
    wireCtoPointMarker: wireCtoPointMarker,
    pinAndOpenCtoTooltip: pinAndOpenCtoTooltip,
    dismissCtoTooltip: dismissCtoTooltip,
    disableCtoTooltipHoverOpen: disableCtoTooltipHoverOpen,
    onCtoMarkerActivate: onCtoMarkerActivate,
    notifyMapCoordCopy: notifyMapCoordCopy,
    rewireMarkerPopupCopy: rewireMarkerPopupCopy,
  };

  function copyMountEl() {
    if (window.NocMapFullscreen && window.NocMapFullscreen.copyMountEl) {
      return window.NocMapFullscreen.copyMountEl();
    }
    var fs =
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.msFullscreenElement;
    return fs || document.body;
  }

  function notifyCopy(msg, opts) {
    opts = opts || {};
    var msgText = msg || "Copiado al portapapeles";
    if (
      opts.toastMsg === "Coordenadas copiadas al portapapeles" ||
      msgText === "Coordenadas copiadas al portapapeles"
    ) {
      notifyMapCoordCopy(msgText, opts);
      return;
    }
    if (
      window.NocMapFullscreen &&
      window.NocMapFullscreen.showActiveToast &&
      window.NocMapFullscreen.showActiveToast(msgText, opts)
    ) {
      return;
    }
    if (opts.toastId && window.NocToast) {
      window.NocToast.show(opts.toastId, msgText, {
        durationMs: opts.durationMs || 1600,
      });
      return;
    }
    if (typeof opts.onSuccess === "function") {
      opts.onSuccess(msgText);
    }
  }

  function copyText(text, opts) {
    opts = opts || {};
    if (!text) {
      if (opts.emptyMsg) notifyCopy(opts.emptyMsg, opts);
      return false;
    }
    var mount = copyMountEl();
    var okMsg = opts.toastMsg || opts.successMsg || "Copiado al portapapeles";
    var failMsg = opts.failMsg || "No se pudo copiar";

    function syncExecCopy() {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "readonly");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        ta.style.top = "0";
        mount.appendChild(ta);
        ta.focus();
        ta.select();
        var ok = document.execCommand("copy");
        mount.removeChild(ta);
        if (ok) {
          notifyCopy(okMsg, opts);
          return true;
        }
      } catch (_syncErr) {}
      return false;
    }

    if (opts.preferSync && syncExecCopy()) {
      return true;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(function () {
          notifyCopy(okMsg, opts);
        })
        .catch(function () {
          if (!syncExecCopy()) notifyCopy(failMsg, opts);
        });
      return true;
    }
    if (syncExecCopy()) return true;
    notifyCopy(failMsg, opts);
    return false;
  }

  window.NocClipboard = {
    copyText: copyText,
    copyMountEl: copyMountEl,
    notifyCopy: notifyCopy,
  };
})();
