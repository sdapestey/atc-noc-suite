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
    rxHistoricoTone: rxHistoricoTone,
    worstRxHistoricoTone: worstRxHistoricoTone,
  };
})();
