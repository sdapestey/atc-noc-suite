/**
 * NOC: atajos de foco en el campo de búsqueda (/ y Ctrl+K; Esc limpia si está en el input).
 */
(function () {
  let _opts = null;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function bindKeys() {
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
})();
