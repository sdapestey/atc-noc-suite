(function () {
  "use strict";

  var CTO_MAP_URL = "/dashboard/rama/cto-map";
  var RAMA_MAP_URL = "/dashboard/rama/rama-map";

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function initCtoMap(shell) {
    if (!shell || shell.dataset.consultaCtoMapReady) return;
    var cto = (shell.getAttribute("data-cto") || "").trim();
    var msg = shell.querySelector(".consulta-cto-map-msg");
    var canvas = shell.querySelector("[data-consulta-cto-mapa-canvas]");
    if (!cto || !msg || !canvas) return;

    shell.dataset.consultaCtoMapReady = "loading";
    msg.textContent = "Cargando ubicación…";
    canvas.hidden = true;

    fetch(CTO_MAP_URL + "?cto=" + encodeURIComponent(cto))
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) {
          msg.textContent = (data && data.error) || "Sin coordenadas para esta CTO";
          canvas.hidden = true;
          shell.dataset.consultaCtoMapReady = "nocords";
          return;
        }
        if (typeof window.L === "undefined") {
          msg.textContent = "No se pudo cargar el mapa (Leaflet).";
          canvas.hidden = true;
          shell.dataset.consultaCtoMapReady = "nocords";
          return;
        }
        var lat = Number(data.lat);
        var lon = Number(data.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
          msg.textContent = "Sin coordenadas para esta CTO";
          canvas.hidden = true;
          shell.dataset.consultaCtoMapReady = "nocords";
          return;
        }
        msg.textContent = "";
        canvas.hidden = false;

        var map = shell._leafletMap;
        if (!map) {
          map = window.L.map(canvas, { attributionControl: true, zoomControl: true }).setView([lat, lon], 17);
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
          requestAnimationFrame(function () {
            map.invalidateSize();
          });
        }
        shell.dataset.consultaCtoMapReady = "done";
      })
      .catch(function () {
        msg.textContent = "No se pudo obtener la ubicación.";
        canvas.hidden = true;
        delete shell.dataset.consultaCtoMapReady;
      });
  }

  function loadRamaMapIntoPanel(panel, rama) {
    var msg = panel.querySelector(".consulta-rama-mapa-msg");
    var footer = panel.querySelector(".consulta-rama-mapa-footer");
    var canvas = panel.querySelector("[data-consulta-rama-mapa-canvas]");
    if (!msg || !canvas) return;

    msg.textContent = "Cargando mapa…";
    if (footer) footer.textContent = "";
    canvas.hidden = true;

    fetch(RAMA_MAP_URL + "?rama=" + encodeURIComponent(rama))
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) {
          msg.textContent = (data && data.error) || "No se pudo cargar el mapa de la RAMA.";
          canvas.hidden = true;
          return;
        }
        var markers = Array.isArray(data.markers) ? data.markers : [];
        var sinCoord = data.ctos_sin_coordenadas != null ? Number(data.ctos_sin_coordenadas) : 0;
        var ctosTotal = data.ctos_total != null ? Number(data.ctos_total) : 0;

        if (markers.length === 0) {
          if (ctosTotal === 0) {
            msg.textContent = "No hay CTO en inventario para esta RAMA.";
          } else {
            msg.textContent = "Ninguna CTO de esta RAMA tiene coordenadas cargadas.";
          }
          canvas.hidden = true;
          if (footer) footer.textContent = sinCoord > 0 ? sinCoord + " CTO sin coordenadas." : "";
          return;
        }

        msg.textContent = "";
        canvas.hidden = false;
        if (footer) {
          var foot = markers.length + " CTO en el mapa";
          if (sinCoord > 0) foot += " · " + sinCoord + " sin coordenadas";
          footer.textContent = foot + ".";
        }

        if (typeof window.L === "undefined") {
          msg.textContent = "No se pudo cargar el mapa (Leaflet).";
          canvas.hidden = true;
          return;
        }

        var map = panel._ramaLeafletMap;
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

        var fg = window.L.featureGroup();
        markers.forEach(function (mk) {
          var la = Number(mk.lat);
          var lo = Number(mk.lon);
          if (!Number.isFinite(la) || !Number.isFinite(lo)) return;
          var marker = window.L.marker([la, lo]);
          marker.bindPopup('<span class="mono">' + escHtml(mk.cto || "") + "</span>", { maxWidth: 320 });
          fg.addLayer(marker);
        });

        if (fg.getLayers().length === 0) {
          msg.textContent = "Coordenadas inválidas en la respuesta.";
          canvas.hidden = true;
          return;
        }

        fg.addTo(map);
        panel._ramaMarkerLayer = fg;

        requestAnimationFrame(function () {
          map.invalidateSize();
          var bounds = fg.getBounds();
          if (markers.length === 1) {
            map.setView(bounds.getCenter(), 17);
          } else {
            map.fitBounds(bounds, { padding: [28, 28], maxZoom: 17 });
          }
        });
      })
      .catch(function () {
        msg.textContent = "No se pudo cargar el mapa.";
        canvas.hidden = true;
      });
  }

  function initConsultaRamaSearchMaps() {
    document.querySelectorAll("[data-consulta-rama-search-map]").forEach(function (panel) {
      var rama = (panel.getAttribute("data-rama") || "").trim();
      if (!rama) return;
      loadRamaMapIntoPanel(panel, rama);
    });
  }

  function initAllCtoMaps() {
    document.querySelectorAll("[data-consulta-cto-map]").forEach(function (el) {
      initCtoMap(el);
    });
  }

  function initAllConsultaMaps() {
    initConsultaRamaSearchMaps();
    initAllCtoMaps();
  }

  window.consultaInitAllCtoMaps = initAllConsultaMaps;
})();
