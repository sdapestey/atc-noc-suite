/**
 * Splash índice: el inline en splash_overlay.html muestra al instante;
 * cierra con fade tras data-autoclose-ms (def. 2600 ms) o click / Escape.
 */
(function () {
  var KEY = "noc_splash_v1";
  var overlay = document.getElementById("noc-splash-overlay");
  if (!overlay || overlay.hasAttribute("hidden")) return;

  var autoMs = parseInt(overlay.getAttribute("data-autoclose-ms") || "2600", 10);
  if (!Number.isFinite(autoMs) || autoMs < 0) autoMs = 2600;

  var leaving = false;
  var autoTimer = null;
  var shownAt = parseInt(overlay.getAttribute("data-splash-shown-at") || "0", 10);
  if (!Number.isFinite(shownAt) || shownAt <= 0) {
    shownAt = Date.now();
    overlay.setAttribute("data-splash-shown-at", String(shownAt));
  }

  function markSplashSeen() {
    try {
      window.sessionStorage.setItem(KEY, "1");
    } catch (e2) {}
  }

  function lockScroll() {
    var root = document.body || document.documentElement;
    if (root) root.classList.add("noc-splash-open");
  }

  function unlockScroll() {
    document.documentElement.classList.remove("noc-splash-open");
    if (document.body) document.body.classList.remove("noc-splash-open");
  }

  function finishHide() {
    leaving = false;
    if (autoTimer != null) {
      clearTimeout(autoTimer);
      autoTimer = null;
    }
    overlay.classList.remove("noc-splash--visible", "noc-splash--in", "noc-splash--leaving");
    overlay.setAttribute("hidden", "");
    overlay.setAttribute("aria-hidden", "true");
    unlockScroll();
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
    document.removeEventListener("keydown", onKeydown);

    leaving = true;
    overlay.classList.remove("noc-splash--in");
    overlay.classList.add("noc-splash--leaving");
    overlay.setAttribute("aria-hidden", "true");

    overlay.addEventListener("transitionend", onTransitionEnd);
    window.setTimeout(function () {
      if (!leaving) return;
      if (overlay.classList.contains("noc-splash--leaving")) {
        overlay.removeEventListener("transitionend", onTransitionEnd);
        finishHide();
      }
    }, 500);
  }

  function scheduleAutoHide() {
    var elapsed = Date.now() - shownAt;
    var wait = Math.max(0, autoMs - elapsed);
    autoTimer = window.setTimeout(function () {
      autoTimer = null;
      window.requestAnimationFrame(function () {
        hide();
      });
    }, wait);
  }

  var backdrop = overlay.querySelector(".noc-splash-backdrop");
  if (backdrop) {
    backdrop.addEventListener("click", hide);
  }

  lockScroll();
  document.addEventListener("keydown", onKeydown);
  scheduleAutoHide();
})();
