/**
 * Splash pantalla completa: solo "/" sin intención de consulta, una vez por pestaña.
 * Fade in al abrir y fade out al cerrar (opacity + transitionend).
 */
(function () {
  var KEY = "noc_splash_v1";
  var overlay = document.getElementById("noc-splash-overlay");
  if (!overlay) return;

  var path = window.location.pathname || "";
  if (path !== "/") return;

  function hasDeepLinkIntent() {
    try {
      var params = new URLSearchParams(window.location.search || "");
      var prefill = (
        params.get("q") ||
        params.get("rama") ||
        params.get("value") ||
        ""
      ).trim();
      return !!prefill;
    } catch (e) {
      return false;
    }
  }

  function markSplashSeen() {
    try {
      window.sessionStorage.setItem(KEY, "1");
    } catch (e2) {}
  }

  if (hasDeepLinkIntent()) {
    markSplashSeen();
    return;
  }

  try {
    if (window.sessionStorage.getItem(KEY) === "1") return;
  } catch (e) {
    return;
  }

  var autoMs = parseInt(overlay.getAttribute("data-autoclose-ms") || "2600", 10);
  if (!Number.isFinite(autoMs) || autoMs < 0) autoMs = 2600;

  var autoTimer = null;
  var leaving = false;

  function finishHide() {
    leaving = false;
    overlay.classList.remove("noc-splash--visible", "noc-splash--in", "noc-splash--leaving");
    overlay.setAttribute("hidden", "");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("noc-splash-open");
    overlay.removeEventListener("transitionend", onTransitionEnd);
    markSplashSeen();
  }

  function onTransitionEnd(ev) {
    if (ev.target !== overlay || ev.propertyName !== "opacity") return;
    finishHide();
  }

  function onKeydown(ev) {
    if (ev.key === "Escape") hide();
  }

  function hide() {
    if (overlay.hasAttribute("hidden") || leaving) return;
    if (autoTimer != null) {
      clearTimeout(autoTimer);
      autoTimer = null;
    }
    document.removeEventListener("keydown", onKeydown);

    leaving = true;
    overlay.classList.remove("noc-splash--in");
    overlay.classList.add("noc-splash--leaving");
    overlay.setAttribute("aria-hidden", "true");

    overlay.addEventListener("transitionend", onTransitionEnd);
    // Si no hay transición (p. ej. reduced motion extremo), cerrar igual
    window.setTimeout(function () {
      if (!leaving) return;
      if (overlay.classList.contains("noc-splash--leaving")) {
        overlay.removeEventListener("transitionend", onTransitionEnd);
        finishHide();
      }
    }, 700);
  }

  function show() {
    overlay.removeAttribute("hidden");
    overlay.setAttribute("aria-hidden", "false");
    overlay.classList.add("noc-splash--visible");
    document.body.classList.add("noc-splash-open");
    document.addEventListener("keydown", onKeydown);

    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        overlay.classList.add("noc-splash--in");
      });
    });

    window.setTimeout(function () {
      try {
        overlay.focus();
      } catch (e3) {}
    }, 120);
    if (autoMs > 0) {
      autoTimer = window.setTimeout(hide, autoMs);
    }
  }

  var backdrop = overlay.querySelector(".noc-splash-backdrop");
  if (backdrop) {
    backdrop.addEventListener("click", function () {
      hide();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", show);
  } else {
    show();
  }
})();
