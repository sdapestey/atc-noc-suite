/**
 * Reloj en la topbar NOC: fecha y hora local del navegador.
 */
(function () {
  function formatClock(date) {
    const d = date.toLocaleDateString("es-AR", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const t = date.toLocaleTimeString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    return d + " · " + t;
  }

  function tick() {
    const now = new Date();
    document.querySelectorAll("[data-noc-clock]").forEach(function (el) {
      el.textContent = formatClock(now);
      if (el.setAttribute) {
        el.setAttribute("datetime", now.toISOString());
      }
    });
  }

  function init() {
    tick();
    window.setInterval(tick, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
