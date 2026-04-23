/**
 * Spinner de pantalla completa al cambiar de pestaña del dashboard (navegación MPA).
 */
(function () {
  var KEY = "dashboardTabNav";

  function setCaptionVisible(on) {
    var el = document.querySelector(".dashboard-tab-nav-loading-caption");
    if (el) el.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function clearLoading() {
    try {
      sessionStorage.removeItem(KEY);
    } catch (e) {}
    document.documentElement.classList.remove("dashboard-tab-nav-loading");
    setCaptionVisible(false);
  }

  function sameDestination(a) {
    try {
      var next = new URL(a.getAttribute("href") || "", location.href);
      return (
        next.pathname === location.pathname &&
        next.search === location.search
      );
    } catch (err) {
      return true;
    }
  }

  document.addEventListener("DOMContentLoaded", clearLoading);

  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      clearLoading();
    }
  });

  document.addEventListener(
    "click",
    function (e) {
      var a = e.target.closest("a.global-tab");
      if (!a || !a.href) return;
      if (
        e.defaultPrevented ||
        e.button !== 0 ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey
      ) {
        return;
      }
      if (sameDestination(a)) return;
      try {
        sessionStorage.setItem(KEY, "1");
      } catch (err) {}
      document.documentElement.classList.add("dashboard-tab-nav-loading");
      setCaptionVisible(true);
    },
    true
  );
})();
