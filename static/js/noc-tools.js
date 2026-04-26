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
})();
