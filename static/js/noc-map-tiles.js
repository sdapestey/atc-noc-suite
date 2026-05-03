/**
 * Basemap Leaflet según data-theme: OSM estándar (light) / Carto Dark Matter (dark).
 * Los tiles estándar de openstreetmap.org no tienen modo noche; en dark usamos CARTO (datos OSM).
 */
(function (global) {
  "use strict";

  var BASE_LIGHT = {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  };

  var BASE_DARK = {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &middot; ' +
      '&copy; <a href="https://carto.com/attributions">CARTO</a>',
  };

  function isLightTheme() {
    return document.documentElement.getAttribute("data-theme") === "light";
  }

  function getBasemapSpec() {
    return isLightTheme() ? BASE_LIGHT : BASE_DARK;
  }

  var subscribers = [];

  function notifyBasemapSubscribers() {
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

  /**
   * Añade la capa base y se re-sincroniza al cambiar data-theme.
   * @param {L.Map} map
   * @param {typeof L} Lref
   * @returns {{ replace: function(): void, unsubscribe: function(): void }}
   */
  function addBasemapLayer(map, Lref) {
    var L = Lref || global.L;
    var layer = null;

    function replace() {
      if (!map || typeof map.getContainer !== "function") return;
      var el = map.getContainer();
      if (!el || !el.parentNode) return;

      var spec = getBasemapSpec();
      if (layer) {
        map.removeLayer(layer);
      }
      layer = L.tileLayer(spec.url, {
        attribution: spec.attribution,
        maxZoom: 19,
      }).addTo(map);
      map.invalidateSize();
    }

    replace();
    var unsub = subscribeBasemap(replace);

    return {
      replace: replace,
      unsubscribe: function () {
        unsub();
      },
    };
  }

  global.NocMapTiles = {
    getBasemapSpec: getBasemapSpec,
    addBasemapLayer: addBasemapLayer,
    subscribeBasemap: subscribeBasemap,
  };
})(typeof window !== "undefined" ? window : this);
