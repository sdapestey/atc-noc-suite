/**
 * Evita que la rueda del mouse sobre el mapa capture el scroll de la página (scroll hijacking).
 * Por defecto scrollWheelZoom está desactivado; al hacer clic en el mapa se habilita el zoom con rueda;
 * al hacer clic fuera del contenedor del mapa se vuelve a desactivar.
 */
(function (global) {
  "use strict";

  function baseMapOptions() {
    return { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
  }

  function attachScrollActivation(map, containerEl) {
    if (!map || !containerEl || !map.scrollWheelZoom) return;

    function disableWheel() {
      map.scrollWheelZoom.disable();
    }

    function enableWheel() {
      map.scrollWheelZoom.enable();
    }

    map.on("click", enableWheel);

    function onDocPointerDown(ev) {
      if (!containerEl.contains(ev.target)) {
        disableWheel();
      }
    }

    document.addEventListener("pointerdown", onDocPointerDown, true);

    map.once("unload", function () {
      document.removeEventListener("pointerdown", onDocPointerDown, true);
      map.off("click", enableWheel);
    });
  }

  global.NocLeafletMap = {
    baseMapOptions: baseMapOptions,
    attachScrollActivation: attachScrollActivation,
  };
})(typeof window !== "undefined" ? window : this);
