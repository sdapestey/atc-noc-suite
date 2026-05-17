(function () {
  "use strict";

  var CTO_MAP_URL = "/dashboard/rama/cto-map";
  var RAMA_MAP_URL = "/dashboard/rama/rama-map";
  var CTO_ADDRESS_URL = "/dashboard/rama/cto-address";

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
          var mapOpts =
            window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
              ? window.NocLeafletMap.baseMapOptions()
              : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
          map = window.L.map(canvas, mapOpts).setView([lat, lon], 17);
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
          if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
            window.NocLeafletMap.attachScrollActivation(map, canvas);
          }
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

  function loadRamaMapIntoPanel(panel) {
    var rama = (panel.getAttribute("data-rama") || "").trim();
    if (!rama) return;
    var msg = panel.querySelector(".consulta-rama-mapa-msg");
    var footer = panel.querySelector(".consulta-rama-mapa-footer");
    var canvas = panel.querySelector("[data-consulta-rama-mapa-canvas]");
    if (!msg || !canvas) return;

    if (panel.dataset.consultaRamaMapFetched === "1" && panel._ramaLeafletMap) {
      requestAnimationFrame(function () {
        panel._ramaLeafletMap.invalidateSize();
      });
      return;
    }

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
          var mapOptsRama =
            window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
              ? window.NocLeafletMap.baseMapOptions()
              : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
          map = window.L.map(canvas, mapOptsRama);
          if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
            panel._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
          } else {
            window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
              attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
              maxZoom: 19,
            }).addTo(map);
          }
          panel._ramaLeafletMap = map;
          if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
            window.NocLeafletMap.attachScrollActivation(map, canvas);
          }
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
        panel.dataset.consultaRamaMapFetched = "1";
      })
      .catch(function () {
        msg.textContent = "No se pudo cargar el mapa.";
        canvas.hidden = true;
      });
  }

  function bindLazyRamaMap(panel) {
    var rama = (panel.getAttribute("data-rama") || "").trim();
    if (!rama) return;
    loadRamaMapIntoPanel(panel);
  }

  function syncRamaMapaToggleButtons(section, expanded) {
    if (!section || !section.querySelectorAll) return;
    section.querySelectorAll("[data-consulta-toggle-rama-mapa]").forEach(function (b) {
      b.textContent = expanded ? "Ocultar mapa" : "Ver mapa";
      b.setAttribute(
        "title",
        expanded ? "Ocultar mapa de CTO en la RAMA" : "Mostrar mapa de CTO en la RAMA"
      );
    });
  }

  function syncCtoMapaToggleButtons(detailsEl, expanded) {
    if (!detailsEl || !detailsEl.id) return;
    var id = detailsEl.id;
    document.querySelectorAll('[data-consulta-cto-mapa-details-id="' + id + '"]').forEach(function (b) {
      b.textContent = expanded ? "Ocultar mapa" : "Ver mapa";
      b.setAttribute(
        "title",
        expanded ? "Ocultar mapa de la CTO" : "Mostrar mapa de la CTO"
      );
    });
  }

  function initConsultaRamaSearchMaps() {
    document.querySelectorAll("[data-consulta-rama-search-map]").forEach(function (panel) {
      var wrap = panel.closest(".consulta-mapa-rama-details");
      if (wrap && wrap.classList.contains("consulta-mapa-rama-details--until-ver-mapa")) {
        return;
      }
      bindLazyRamaMap(panel);
    });
  }

  function bindLazyCtoMap(shell) {
    var det = shell.closest("details.consulta-mapa-cto-details");
    function run() {
      initCtoMap(shell);
    }
    if (det) {
      if (!det.classList.contains("consulta-mapa-cto-details--until-ver-mapa")) {
        if (det.open) run();
        det.addEventListener("toggle", function () {
          if (det.open) run();
        });
        return;
      }
      if (det.getAttribute("data-consulta-mapa-revealed") === "1" && det.open) run();
      det.addEventListener("toggle", function () {
        if (det.classList.contains("consulta-mapa-cto-details--until-ver-mapa")) {
          if (det.open) {
            det.setAttribute("data-consulta-mapa-revealed", "1");
            syncCtoMapaToggleButtons(det, true);
          } else {
            det.removeAttribute("data-consulta-mapa-revealed");
            syncCtoMapaToggleButtons(det, false);
          }
        }
        if (det.open) run();
      });
      return;
    }
    run();
  }

  function initAllCtoMaps() {
    document.querySelectorAll("[data-consulta-cto-map]").forEach(bindLazyCtoMap);
  }

  function initConsultaCtoPostalRows() {
    document.querySelectorAll("[data-consulta-cto-postal-fetch]").forEach(function (el) {
      if (el.dataset.consultaPostalInit === "1") return;
      el.dataset.consultaPostalInit = "1";
      var cto = (el.getAttribute("data-cto") || "").trim();
      if (!cto) {
        el.classList.remove("consulta-cto-ficha__row--loading");
        el.innerHTML =
          '<span class="consulta-cto-ficha__label">Dirección</span>' +
          '<span class="consulta-cto-ficha__value consulta-cto-ficha__value--muted">—</span>';
        return;
      }
      fetch(CTO_ADDRESS_URL + "?cto=" + encodeURIComponent(cto))
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          el.classList.remove("consulta-cto-ficha__row--loading");
          if (data && data.ok && data.address) {
            var addr = escHtml(String(data.address).trim());
            el.innerHTML =
              '<span class="consulta-cto-ficha__label">Dirección</span>' +
              '<span class="consulta-cto-ficha__value">' +
              addr +
              "</span>";
          } else {
            el.innerHTML =
              '<span class="consulta-cto-ficha__label">Dirección</span>' +
              '<span class="consulta-cto-ficha__value consulta-cto-ficha__value--muted">Sin datos en CM</span>';
          }
        })
        .catch(function () {
          el.classList.remove("consulta-cto-ficha__row--loading");
          el.innerHTML =
            '<span class="consulta-cto-ficha__label">Dirección</span>' +
            '<span class="consulta-cto-ficha__value consulta-cto-ficha__value--muted">No se pudo cargar</span>';
          delete el.dataset.consultaPostalInit;
        });
    });
  }

  function initAllConsultaMaps() {
    initConsultaRamaSearchMaps();
    initAllCtoMaps();
    initConsultaCtoPostalRows();
  }

  window.consultaInitAllCtoMaps = initAllConsultaMaps;

  window.consultaAbrirMapaRama = function (btn) {
    var sec = btn && btn.closest ? btn.closest(".consulta-section") : null;
    if (!sec) return;
    var wrap = sec.querySelector(".consulta-mapa-rama-details");
    if (!wrap) return;

    var expanded = wrap.getAttribute("data-consulta-mapa-revealed") === "1";

    if (expanded) {
      wrap.removeAttribute("data-consulta-mapa-revealed");
      syncRamaMapaToggleButtons(sec, false);
      return;
    }

    wrap.setAttribute("data-consulta-mapa-revealed", "1");
    syncRamaMapaToggleButtons(sec, true);

    var panel = wrap.querySelector("[data-consulta-rama-search-map]");
    if (panel) {
      loadRamaMapIntoPanel(panel);
    }

    if (wrap.scrollIntoView) {
      wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  window.consultaAbrirMapaCto = function (btn) {
    if (!btn) return;
    var targetId = (btn.getAttribute("data-consulta-cto-mapa-details-id") || "").trim();
    var det = targetId ? document.getElementById(targetId) : null;
    if (!det || String(det.tagName || "").toLowerCase() !== "details") {
      var block = btn.closest(".consulta-cto-block");
      det = block ? block.querySelector("details.consulta-mapa-cto-details") : null;
      if (!det) {
        var sec = btn.closest(".consulta-section");
        det = sec ? sec.querySelector("details.consulta-mapa-cto-details") : null;
      }
    }
    if (!det) return;

    if (!det.classList.contains("consulta-mapa-cto-details--until-ver-mapa")) {
      det.open = !det.open;
      return;
    }

    var shell = det.querySelector("[data-consulta-cto-map]");
    var expanded = det.getAttribute("data-consulta-mapa-revealed") === "1" && det.open;

    if (expanded) {
      det.open = false;
      det.removeAttribute("data-consulta-mapa-revealed");
      syncCtoMapaToggleButtons(det, false);
      return;
    }

    det.setAttribute("data-consulta-mapa-revealed", "1");
    det.open = true;
    syncCtoMapaToggleButtons(det, true);
    if (shell) initCtoMap(shell);
    if (det.scrollIntoView) {
      det.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };
})();
