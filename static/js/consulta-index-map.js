(function () {
  "use strict";

  var CTO_MAP_URL = "/dashboard/rama/cto-map";
  var RAMA_MAP_URL = "/dashboard/rama/rama-map";
  var CTO_ADDRESS_URL = "/dashboard/rama/cto-address";
  var RAMA_CAMINO_GIS_URL = "/dashboard/camino-optico/gis";

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showConsultaToast(msg) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    if (showConsultaToast._timer) clearTimeout(showConsultaToast._timer);
    showConsultaToast._timer = setTimeout(function () {
      el.classList.remove("show");
    }, 1800);
  }

  function copyCoordsToClipboard(text) {
    var done = function () {
      showConsultaToast("Coordenadas copiadas al portapapeles");
    };
    var fail = function () {
      showConsultaToast("No se pudo copiar");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(done).catch(function () {
        fallback();
      });
    }
    fallback();
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try {
        if (document.execCommand("copy")) done();
        else fail();
      } catch (_e) {
        fail();
      }
      document.body.removeChild(ta);
    }
  }

  function coordTextFromLatLon(lat, lon) {
    var latN = Number(lat);
    var lonN = Number(lon);
    if (!Number.isFinite(latN) || !Number.isFinite(lonN)) return "";
    return latN.toFixed(6) + ", " + lonN.toFixed(6);
  }

  function markerPopupHtml(cto, lat, lon, addr, opts) {
    var coordText = coordTextFromLatLon(lat, lon);
    var showAddrLoading = opts && opts.showAddrLoading;
    return (
      '<div class="camino-popup-cto">' +
      '<div class="camino-popup-cto__id"><strong>' +
      escHtml(cto || "") +
      "</strong></div>" +
      '<div class="camino-popup-cto__addr" data-rama-popup-addr>' +
      (addr
        ? '<span class="camino-popup-addr">' + escHtml(addr) + "</span>"
        : showAddrLoading
        ? '<span class="muted">Buscando dirección…</span>'
        : '<span class="muted">Sin dirección postal</span>') +
      "</div>" +
      (coordText
        ? '<div class="camino-popup-cto__coords mono" title="Latitud, Longitud">' +
          escHtml(coordText) +
          "</div>"
        : "") +
      (coordText
        ? '<div class="camino-popup-cto__copy muted">Click en la CTO para copiar coordenadas</div>'
        : "") +
      "</div>"
    );
  }

  function markerHoverStyle(base) {
    return {
      radius: Math.min((base.radius || 9) + 5, 22),
      fillColor: base.fillColor,
      color: base.color,
      weight: Math.min((base.weight || 2) + 2, 5),
      opacity: base.opacity,
      fillOpacity: Math.min((base.fillOpacity != null ? base.fillOpacity : 0.95) + 0.04, 1),
    };
  }

  function wireConsultaCtoMarker(cm, tooltipHtml, styleBase, coordText) {
    var base = {};
    Object.keys(styleBase || {}).forEach(function (k) {
      base[k] = styleBase[k];
    });
    cm._consultaBaseOpts = base;
    cm._consultaHoverOpts = markerHoverStyle(base);
    cm.bindTooltip(tooltipHtml, {
      direction: "top",
      opacity: 0.96,
      className: "camino-popup-cto camino-cto-hover-tip",
      interactive: false,
    });
    cm.on("mouseover", function () {
      cm.setStyle(cm._consultaHoverOpts);
      try {
        cm.bringToFront();
      } catch (_e) {}
    });
    cm.on("mouseout", function () {
      cm.setStyle(cm._consultaBaseOpts);
    });
    cm.on("click", function (ev) {
      if (window.L && window.L.DomEvent && ev) {
        window.L.DomEvent.stopPropagation(ev);
      }
      if (!coordText) return;
      copyCoordsToClipboard(coordText);
    });
  }

  function extendBoundsFromGeoJSON(bounds, gj) {
    if (!gj || !Array.isArray(gj.features)) return;
    var depthByType = {
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
      if (Array.isArray(coords)) coords.forEach(function (c) {
        scan(c, depth - 1);
      });
    }
    gj.features.forEach(function (f) {
      var g = f && f.geometry;
      if (!g || !g.coordinates) return;
      var d = depthByType[g.type];
      if (d != null) scan(g.coordinates, d);
    });
  }

  function fitMapToData(map, gj, markers) {
    var b = window.L.latLngBounds([]);
    if (gj) extendBoundsFromGeoJSON(b, gj);
    (markers || []).forEach(function (m) {
      var lat = Number(m.lat);
      var lon = Number(m.lon);
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

  function refreshMapTiles(map, basemapCtrl) {
    if (basemapCtrl && typeof basemapCtrl.redraw === "function") {
      basemapCtrl.redraw();
    } else if (map && window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
      window.NocMapTiles.refreshLeafletMapLayout(map);
      setTimeout(function () {
        if (map && window.NocMapTiles) window.NocMapTiles.refreshLeafletMapLayout(map);
      }, 120);
    }
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
          if (window.NocMapTiles && window.NocMapTiles.createLeafletMap) {
            var created = window.NocMapTiles.createLeafletMap(canvas, { lat: lat, lon: lon, zoom: 17, marker: false });
            if (created) {
              shell._leafletMap = created.map;
              shell._nocMapBasemap = created.basemap;
            }
          }
          if (!shell._leafletMap) {
            var mapOpts =
              window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
                ? window.NocLeafletMap.baseMapOptions()
                : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
            map = window.L.map(canvas, mapOpts).setView([lat, lon], 17);
            window.L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
              attribution: "&copy; OpenStreetMap &copy; CARTO",
              maxZoom: 19,
            }).addTo(map);
            shell._leafletMap = map;
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
        }
        map = shell._leafletMap;
        if (shell._consultaCtoPointLayer) {
          map.removeLayer(shell._consultaCtoPointLayer);
          shell._consultaCtoPointLayer = null;
        }
        var coordText = coordTextFromLatLon(lat, lon);
        var pointStyle = {
          radius: 9,
          fillColor: "#f97316",
          color: "#e0f2fe",
          weight: 2,
          opacity: 1,
          fillOpacity: 0.95,
        };
        var marker = window.L.circleMarker([lat, lon], pointStyle);
        wireConsultaCtoMarker(
          marker,
          markerPopupHtml(cto, lat, lon, "", { showAddrLoading: true }),
          pointStyle,
          coordText
        );
        marker._consultaAddrResolved = false;
        marker.on("mouseover", function () {
          if (marker._consultaAddrResolved) return;
          marker._consultaAddrResolved = true;
          fetch(CTO_ADDRESS_URL + "?cto=" + encodeURIComponent(cto))
            .then(function (r) {
              return r.ok ? r.json() : null;
            })
            .then(function (dataAddr) {
              var addr =
                dataAddr && dataAddr.ok && dataAddr.address ? String(dataAddr.address).trim() : "";
              marker.setTooltipContent(
                markerPopupHtml(cto, lat, lon, addr, { showAddrLoading: false })
              );
            })
            .catch(function () {
              marker.setTooltipContent(
                markerPopupHtml(cto, lat, lon, "", { showAddrLoading: false })
              );
            });
        });
        shell._consultaCtoPointLayer = window.L.layerGroup([marker]).addTo(map);
        map.setView([lat, lon], 17);
        refreshMapTiles(map, shell._nocMapBasemap);
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
      if (window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
        window.NocMapTiles.refreshLeafletMapLayout(panel._ramaLeafletMap);
      }
      return;
    }

    msg.textContent = "Cargando mapa…";
    if (footer) footer.textContent = "";
    canvas.hidden = true;

    Promise.all([
      fetch(RAMA_MAP_URL + "?rama=" + encodeURIComponent(rama)).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }),
      fetch(RAMA_CAMINO_GIS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ rama: rama }),
      })
        .then(function (r) {
          return r.ok ? r.json() : { ok: false, error: "Error HTTP GIS" };
        })
        .catch(function () {
          return { ok: false, error: "Error GIS" };
        }),
    ])
      .then(function (resp) {
        var data = resp[0];
        var gis = resp[1];
        if (!data || !data.ok) {
          msg.textContent = (data && data.error) || "No se pudo cargar el mapa de la RAMA.";
          canvas.hidden = true;
          return;
        }
        var markers = Array.isArray(data.markers) ? data.markers : [];
        var sinCoord = data.ctos_sin_coordenadas != null ? Number(data.ctos_sin_coordenadas) : 0;
        var ctosTotal = data.ctos_total != null ? Number(data.ctos_total) : 0;
        var gj = gis && gis.ok && gis.geojson ? gis.geojson : null;
        var hasPath = !!(gj && Array.isArray(gj.features) && gj.features.length > 0);

        if (markers.length === 0 && !hasPath) {
          if (ctosTotal === 0) {
            msg.textContent = "No hay CTO en inventario para esta RAMA.";
          } else {
            msg.textContent = "Ninguna CTO de esta RAMA tiene coordenadas cargadas.";
          }
          if (gis && gis.error) msg.textContent += " " + gis.error;
          canvas.hidden = true;
          if (footer) footer.textContent = sinCoord > 0 ? sinCoord + " CTO sin coordenadas." : "";
          return;
        }

        msg.textContent = "";
        canvas.hidden = false;
        if (footer) {
          var foot = markers.length + " CTO en el mapa";
          if (sinCoord > 0) foot += " · " + sinCoord + " sin coordenadas";
          if (hasPath) foot += " · trazado ci_op visible";
          footer.textContent = foot + ".";
        }

        if (typeof window.L === "undefined") {
          msg.textContent = "No se pudo cargar el mapa (Leaflet).";
          canvas.hidden = true;
          return;
        }

        var map = panel._ramaLeafletMap;
        if (!map) {
          if (window.NocMapTiles && window.NocMapTiles.createLeafletMap) {
            var createdR = window.NocMapTiles.createLeafletMap(canvas, { marker: false, zoom: 11 });
            if (createdR) {
              map = createdR.map;
              panel._nocMapBasemap = createdR.basemap;
            }
          }
          if (!map) {
            var mapOptsRama =
              window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
                ? window.NocLeafletMap.baseMapOptions()
                : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
            map = window.L.map(canvas, mapOptsRama);
            if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
              panel._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
            }
            if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
              window.NocLeafletMap.attachScrollActivation(map, canvas);
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
              interactive: false,
              style: function () {
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

        var fg = window.L.featureGroup();
        markers.forEach(function (mk) {
          var lat = Number(mk.lat);
          var lon = Number(mk.lon);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
          var pointStyle = {
            radius: 9,
            fillColor: "#3b82f6",
            color: "#e0f2fe",
            weight: 2,
            opacity: 1,
            fillOpacity: 0.95,
          };
          var cto = String(mk.cto || "").trim();
          var marker = window.L.circleMarker([lat, lon], pointStyle);
          var coordText = coordTextFromLatLon(lat, lon);
          wireConsultaCtoMarker(
            marker,
            markerPopupHtml(cto, lat, lon, "", { showAddrLoading: true }),
            pointStyle,
            coordText
          );
          marker._consultaAddrResolved = false;
          marker.on("mouseover", function () {
            if (!cto || marker._consultaAddrResolved) return;
            marker._consultaAddrResolved = true;
            fetch(CTO_ADDRESS_URL + "?cto=" + encodeURIComponent(cto))
              .then(function (r) {
                return r.ok ? r.json() : null;
              })
              .then(function (dataAddr) {
                var addr =
                  dataAddr && dataAddr.ok && dataAddr.address ? String(dataAddr.address).trim() : "";
                marker.setTooltipContent(
                  markerPopupHtml(cto, lat, lon, addr, { showAddrLoading: false })
                );
              })
              .catch(function () {
                marker.setTooltipContent(
                  markerPopupHtml(cto, lat, lon, "", { showAddrLoading: false })
                );
              });
          });
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
          if (!fitMapToData(map, gj, markers)) {
            map.setView([-34.6, -58.38], 11);
          }
          refreshMapTiles(map, panel._nocMapBasemap);
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
    if (window.ConsultaMasivoUi && sec.classList.contains("consulta-section--multi")) {
      window.ConsultaMasivoUi.expandRamaSection(sec, { expandCtos: true });
    }
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
    var secCto = btn.closest ? btn.closest(".consulta-section") : null;
    if (
      window.ConsultaMasivoUi &&
      secCto &&
      secCto.classList.contains("consulta-section--multi")
    ) {
      window.ConsultaMasivoUi.expandRamaSection(secCto, { expandCtos: true });
    }
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
