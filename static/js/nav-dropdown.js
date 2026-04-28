/**
 * Menú desplegable de secciones (navegación) en viewports estrechos.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-nav-dropdown]");
    if (!root) return;

    var btn = root.querySelector(".global-nav-dd-trigger");
    var menu = document.getElementById("global-nav-dd-menu");
    if (!btn || !menu) return;

    var backdrop = root.querySelector(".global-nav-dd-backdrop");
    var mq = window.matchMedia("(min-width: 900px)");
    var open = false;
    var transitionMs = 220;

    function isDesktop() {
      return mq.matches;
    }

    function setOpen(next) {
      if (open === next) return;
      open = next;

      if (next) {
        menu.removeAttribute("hidden");
        if (backdrop) {
          backdrop.removeAttribute("hidden");
        }
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            root.classList.add("is-open");
            menu.classList.add("is-open");
            if (backdrop) {
              backdrop.classList.add("is-open");
              backdrop.setAttribute("aria-hidden", "false");
            }
            btn.setAttribute("aria-expanded", "true");
            menu.setAttribute("aria-hidden", "false");
          });
        });
      } else {
        root.classList.remove("is-open");
        menu.classList.remove("is-open");
        if (backdrop) {
          backdrop.classList.remove("is-open");
          backdrop.setAttribute("aria-hidden", "true");
        }
        btn.setAttribute("aria-expanded", "false");
        menu.setAttribute("aria-hidden", "true");
        setTimeout(function () {
          if (!open) {
            menu.setAttribute("hidden", "hidden");
            if (backdrop) {
              backdrop.setAttribute("hidden", "hidden");
            }
          }
        }, transitionMs);
      }
    }

    function close() {
      setOpen(false);
    }

    btn.addEventListener("click", function (e) {
      if (isDesktop()) return;
      e.preventDefault();
      e.stopPropagation();
      setOpen(!open);
    });

    if (backdrop) {
      backdrop.addEventListener("click", function () {
        close();
      });
    }

    document.addEventListener("click", function (e) {
      if (!open || isDesktop()) return;
      if (root && !root.contains(e.target)) {
        close();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && open && !isDesktop()) {
        e.preventDefault();
        close();
        try {
          btn.focus();
        } catch (err) {}
      }
    });

    function onMqChange() {
      if (isDesktop() && open) {
        setOpen(false);
      }
    }

    if (mq.addEventListener) {
      mq.addEventListener("change", onMqChange);
    } else {
      mq.addListener(onMqChange);
    }
  });
})();
