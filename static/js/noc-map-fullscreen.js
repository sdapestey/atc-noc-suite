/**
 * Pantalla completa para mapas Leaflet NOC (RAMA, CTO, consulta).
 * Usa Fullscreen API sobre un contenedor que envuelve el canvas del mapa.
 */
(function (global) {
  "use strict";

  var FS_BTN_INNER =
    '<svg class="noc-map-fs-icon noc-map-fs-icon--open" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>' +
    "</svg>" +
    '<svg class="noc-map-fs-icon noc-map-fs-icon--close" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>' +
    "</svg>";

  function fsActiveEl() {
    return (
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.msFullscreenElement ||
      null
    );
  }

  function isWrapFullscreen(wrap) {
    return !!(wrap && fsActiveEl() === wrap);
  }

  function enterFs(wrap) {
    if (!wrap) return;
    var req =
      wrap.requestFullscreen || wrap.webkitRequestFullscreen || wrap.msRequestFullscreen;
    if (!req) return;
    try {
      var ret = req.call(wrap);
      if (ret && typeof ret.then === "function") ret.catch(function () {});
    } catch (_e) {}
  }

  function exitFs() {
    var ex =
      document.exitFullscreen || document.webkitExitFullscreen || document.msExitFullscreen;
    if (!ex) return;
    try {
      var ret = ex.call(document);
      if (ret && typeof ret.then === "function") ret.catch(function () {});
    } catch (_e2) {}
  }

  function syncUi(wrap, btn, map) {
    if (!wrap || !btn) return;
    var on = isWrapFullscreen(wrap);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.setAttribute(
      "aria-label",
      on ? "Salir de pantalla completa" : "Ver mapa en pantalla completa"
    );
    btn.title = on ? "Salir de pantalla completa" : "Pantalla completa";
    btn.classList.toggle("noc-map-fs-btn--active", on);
    if (map && global.NocMapTiles && global.NocMapTiles.refreshLeafletMapLayout) {
      global.NocMapTiles.refreshLeafletMapLayout(map);
      setTimeout(function () {
        if (map && global.NocMapTiles) global.NocMapTiles.refreshLeafletMapLayout(map);
      }, 280);
    }
  }

  function ensureWrap(container) {
    if (!container || !container.parentNode) return null;
    var existing = container.closest(".noc-map-fs-wrap");
    if (existing) return existing;
    var wrap = document.createElement("div");
    wrap.className = "noc-map-fs-wrap";
    container.parentNode.insertBefore(wrap, container);
    wrap.appendChild(container);
    return wrap;
  }

  /**
   * @param {L.Map} map
   * @param {HTMLElement} [containerEl] canvas Leaflet (por defecto map.getContainer())
   * @returns {HTMLElement|null} wrap
   */
  function attachMapFullscreen(map, containerEl) {
    if (!map) return null;
    var canvas = containerEl || map.getContainer();
    if (!canvas) return null;
    var wrap = ensureWrap(canvas);
    if (!wrap) return null;

    var btn = wrap.querySelector(".noc-map-fs-btn");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "noc-map-fs-btn";
      btn.innerHTML = FS_BTN_INNER;
      wrap.insertBefore(btn, wrap.firstChild);
    }

    if (wrap._nocFsMap === map && wrap._nocFsBound) return wrap;
    wrap._nocFsMap = map;
    wrap._nocFsBound = true;

    function onClick() {
      if (isWrapFullscreen(wrap)) exitFs();
      else enterFs(wrap);
    }

    function onFsChange() {
      syncUi(wrap, btn, map);
    }

    btn.removeEventListener("click", wrap._nocFsOnClick || function () {});
    wrap._nocFsOnClick = onClick;
    btn.addEventListener("click", onClick);

    if (!wrap._nocFsDocBound) {
      wrap._nocFsDocBound = true;
      document.addEventListener("fullscreenchange", onFsChange);
      document.addEventListener("webkitfullscreenchange", onFsChange);
      document.addEventListener("MSFullscreenChange", onFsChange);
    }

    map.once("unload", function () {
      if (isWrapFullscreen(wrap)) exitFs();
      wrap._nocFsBound = false;
      wrap._nocFsMap = null;
    });

    syncUi(wrap, btn, map);
    return wrap;
  }

  global.NocMapFullscreen = {
    attachMapFullscreen: attachMapFullscreen,
    isWrapFullscreen: isWrapFullscreen,
    exitFullscreen: exitFs,
  };
})(typeof window !== "undefined" ? window : this);
