/**
 * Spinner de pantalla completa al cambiar de pestaña del dashboard (navegación MPA).
 */
(function () {
  var KEY = "dashboardTabNav";
  var COLLAPSE_KEY = "dashboardTabNavForceCollapse";

  function normalizePath(path) {
    var p = String(path || "").trim();
    if (!p) return "/";
    if (p.length > 1 && p.endsWith("/")) return p.slice(0, -1);
    return p;
  }

  function shouldForceCollapseOnSwitch(_fromPath, toPath) {
    var to = normalizePath(toPath);
    var toOlt = to === "/dashboard/olt";
    // Desde cualquier pestaña, si el destino es un dashboard pesado en árbol,
    // se fuerza inicio colapsado para evitar restaurar expansiones previas.
    return toOlt;
  }

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

  function saveCollapseHint(targetPath) {
    try {
      sessionStorage.setItem(
        COLLAPSE_KEY,
        JSON.stringify({
          targetPath: normalizePath(targetPath),
          ts: Date.now(),
        })
      );
    } catch (_err) {}
  }

  function consumeCollapseHint(targetPath) {
    try {
      var raw = sessionStorage.getItem(COLLAPSE_KEY);
      if (!raw) return false;
      sessionStorage.removeItem(COLLAPSE_KEY);
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return false;
      if (normalizePath(parsed.targetPath) !== normalizePath(targetPath)) return false;
      var ageMs = Date.now() - Number(parsed.ts || 0);
      return ageMs >= 0 && ageMs <= 120000;
    } catch (_err) {
      try {
        sessionStorage.removeItem(COLLAPSE_KEY);
      } catch (_innerErr) {}
      return false;
    }
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
      if (a.target === "_blank" || a.classList.contains("global-tab--external")) return;
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
      var nextPath = "";
      try {
        nextPath = new URL(a.getAttribute("href") || "", location.href).pathname || "";
      } catch (_errPath) {}
      if (shouldForceCollapseOnSwitch(location.pathname || "", nextPath)) {
        saveCollapseHint(nextPath);
      }
      try {
        sessionStorage.setItem(KEY, "1");
      } catch (err) {}
      document.documentElement.classList.add("dashboard-tab-nav-loading");
      setCaptionVisible(true);
    },
    true
  );

  window.consumeDashboardTabForceCollapse = function (targetPath) {
    return consumeCollapseHint(targetPath || (location && location.pathname) || "/");
  };
})();
