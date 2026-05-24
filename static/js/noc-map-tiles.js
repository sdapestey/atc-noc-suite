/**
 * Basemap Leaflet según data-theme: solo CARTO CDN (Voyager claro / dark_all oscuro).
 * No usamos tile.openstreetmap.org: en muchas redes está bloqueado o limitado.
 */
(function (global) {
  "use strict";

  /** Voyager: calles y etiquetas más legibles en fondo claro. */
  var BASE_LIGHT = {
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &middot; ' +
      '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
  };

  var BASE_DARK = {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &middot; ' +
      '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
  };

  function isLightTheme() {
    return document.documentElement.getAttribute("data-theme") === "light";
  }

  function getBasemapSpec() {
    return isLightTheme() ? BASE_LIGHT : BASE_DARK;
  }

  var subscribers = [];
  var lastThemeKey = "";

  function themeKey() {
    return document.documentElement.getAttribute("data-theme") || "";
  }

  function notifyBasemapSubscribers() {
    var key = themeKey();
    if (key === lastThemeKey) return;
    lastThemeKey = key;
    subscribers.forEach(function (fn) {
      try {
        fn();
      } catch (_e) {}
    });
  }

  function subscribeBasemap(fn) {
    subscribers.push(fn);
    return function unsubscribe() {
      var i = subscribers.indexOf(fn);
      if (i >= 0) subscribers.splice(i, 1);
    };
  }

  if (typeof MutationObserver !== "undefined") {
    lastThemeKey = themeKey();
    var mo = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === "data-theme") {
          notifyBasemapSubscribers();
          return;
        }
      }
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  var _layoutTimers = typeof WeakMap !== "undefined" ? new WeakMap() : null;

  /** Solo recalcula tamaño del contenedor; no llama layer.redraw() (evita abortar tiles). */
  function refreshLeafletMapLayout(map) {
    if (!map || typeof map.invalidateSize !== "function") return;
    if (_layoutTimers) {
      var prev = _layoutTimers.get(map);
      if (prev) clearTimeout(prev);
      var t = setTimeout(function () {
        _layoutTimers.delete(map);
        try {
          map.invalidateSize({ pan: false, animate: false });
        } catch (_e) {}
      }, 80);
      _layoutTimers.set(map, t);
      return;
    }
    requestAnimationFrame(function () {
      try {
        map.invalidateSize({ pan: false, animate: false });
      } catch (_e) {}
    });
  }

  function _addTileLayerToMap(map, L, spec) {
    return L.tileLayer(spec.url, {
      attribution: spec.attribution,
      maxZoom: 20,
      minZoom: 0,
      keepBuffer: 3,
      updateWhenIdle: true,
      updateWhenZooming: true,
      subdomains: spec.subdomains || "abcd",
    });
  }

  /**
   * Añade la capa base y se re-sincroniza solo si cambia data-theme.
   */
  function addBasemapLayer(map, Lref) {
    var L = Lref || global.L;
    var layer = null;

    function replace() {
      if (!map || typeof map.getContainer !== "function") return;
      var el = map.getContainer();
      if (!el || !el.parentNode) return;

      if (layer) {
        map.removeLayer(layer);
      }
      layer = _addTileLayerToMap(map, L, getBasemapSpec());
      layer.addTo(map);
      refreshLeafletMapLayout(map);
    }

    replace();
    var unsub = subscribeBasemap(replace);

    return {
      replace: replace,
      redraw: function () {
        refreshLeafletMapLayout(map);
      },
      unsubscribe: function () {
        unsub();
      },
    };
  }

  /**
   * Crea mapa + basemap + marcador opcional. Usar tras hacer visible el contenedor.
   */
  function createLeafletMap(canvas, options) {
    var L = global.L;
    if (!L || !canvas) return null;
    options = options || {};

    var mapOpts =
      options.mapOptions ||
      (global.NocLeafletMap && global.NocLeafletMap.baseMapOptions
        ? global.NocLeafletMap.baseMapOptions()
        : { attributionControl: true, zoomControl: true, scrollWheelZoom: false });

    var lat = Number(options.lat);
    var lon = Number(options.lon);
    var zoom = options.zoom != null ? options.zoom : 17;
    var map = L.map(canvas, mapOpts);
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      map.setView([lat, lon], zoom);
    }

    var basemap = addBasemapLayer(map, L);
    var marker = null;
    if (options.marker !== false && Number.isFinite(lat) && Number.isFinite(lon)) {
      marker = L.marker([lat, lon]).addTo(map);
      map._nocSingleMarker = marker;
    }

    if (global.NocLeafletMap && global.NocLeafletMap.attachScrollActivation) {
      global.NocLeafletMap.attachScrollActivation(map, canvas);
    }

    if (options.fullscreen !== false && global.NocMapFullscreen) {
      global.NocMapFullscreen.attachMapFullscreen(map, canvas);
    }

    refreshLeafletMapLayout(map);

    return { map: map, basemap: basemap, marker: marker };
  }

  function updateMapMarker(map, lat, lon, zoom) {
    var L = global.L;
    if (!map || !L) return;
    var la = Number(lat);
    var lo = Number(lon);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) return;

    if (map._nocSingleMarker) {
      try {
        map.removeLayer(map._nocSingleMarker);
      } catch (_e) {}
      map._nocSingleMarker = null;
    }
    map._nocSingleMarker = L.marker([la, lo]).addTo(map);
    var z = zoom != null ? zoom : map.getZoom() || 17;
    map.setView([la, lo], z);
    refreshLeafletMapLayout(map);
  }

  global.NocMapTiles = {
    getBasemapSpec: getBasemapSpec,
    addBasemapLayer: addBasemapLayer,
    subscribeBasemap: subscribeBasemap,
    refreshLeafletMapLayout: refreshLeafletMapLayout,
    createLeafletMap: createLeafletMap,
    updateMapMarker: updateMapMarker,
  };
})(typeof window !== "undefined" ? window : this);
