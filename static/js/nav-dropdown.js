/**
 * Menú desplegable de navegación: móvil (lista completa) y grupos en desktop.
 * Apertura/cierre con fade + slide (opacity / transform, ~220ms).
 */
(function () {
  "use strict";

  var mq = window.matchMedia("(min-width: 900px)");
  var transitionMs = 220;
  var openRoots = [];

  function isDesktop() {
    return mq.matches;
  }

  function isMobileDropdown(root) {
    return root.hasAttribute("data-nav-mobile-only");
  }

  function isDesktopGroup(root) {
    return root.hasAttribute("data-nav-desktop-group");
  }

  function isEnabled(root) {
    if (isMobileDropdown(root)) return !isDesktop();
    if (isDesktopGroup(root)) return isDesktop();
    return true;
  }

  function getTrigger(root) {
    return root.querySelector(".global-nav-dd-trigger, .global-nav-group-trigger");
  }

  function getMenu(root) {
    return root.querySelector(".global-nav-dd-menu, .global-nav-group-menu");
  }

  function getBackdrop(root) {
    return root.querySelector(".global-nav-dd-backdrop");
  }

  function setOpen(root, next) {
    var btn = getTrigger(root);
    var menu = getMenu(root);
    if (!btn || !menu) return;

    var backdrop = getBackdrop(root);
    var wasOpen = root.classList.contains("is-open");

    if (wasOpen === next) return;

    if (next) {
      openRoots.forEach(function (other) {
        if (other !== root) setOpen(other, false);
      });
      openRoots = openRoots.filter(function (other) {
        return other !== root;
      });
      openRoots.push(root);

      menu.removeAttribute("hidden");
      if (backdrop) backdrop.removeAttribute("hidden");
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
      return;
    }

    root.classList.remove("is-open");
    menu.classList.remove("is-open");
    if (backdrop) {
      backdrop.classList.remove("is-open");
      backdrop.setAttribute("aria-hidden", "true");
    }
    btn.setAttribute("aria-expanded", "false");
    menu.setAttribute("aria-hidden", "true");
    openRoots = openRoots.filter(function (other) {
      return other !== root;
    });

    window.setTimeout(function () {
      if (!root.classList.contains("is-open")) {
        menu.setAttribute("hidden", "hidden");
        if (backdrop) backdrop.setAttribute("hidden", "hidden");
      }
    }, transitionMs);
  }

  function closeAll() {
    openRoots.slice().forEach(function (root) {
      setOpen(root, false);
    });
  }

  function initDropdown(root) {
    var btn = getTrigger(root);
    var menu = getMenu(root);
    if (!btn || !menu) return;

    var backdrop = getBackdrop(root);

    btn.addEventListener("click", function (e) {
      if (!isEnabled(root)) return;
      e.preventDefault();
      e.stopPropagation();
      setOpen(root, !root.classList.contains("is-open"));
    });

    menu.querySelectorAll("a[href]").forEach(function (link) {
      link.addEventListener("click", function () {
        if (isEnabled(root)) setOpen(root, false);
      });
    });

    if (backdrop) {
      backdrop.addEventListener("click", function () {
        setOpen(root, false);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-nav-dropdown]").forEach(initDropdown);

    document.addEventListener("click", function (e) {
      if (!openRoots.length) return;
      var inside = false;
      openRoots.forEach(function (root) {
        if (root.contains(e.target)) inside = true;
      });
      if (!inside) closeAll();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || !openRoots.length) return;
      var focusRoot = null;
      openRoots.forEach(function (root) {
        if (root.contains(document.activeElement)) focusRoot = root;
      });
      e.preventDefault();
      closeAll();
      if (focusRoot) {
        var btn = getTrigger(focusRoot);
        if (btn) {
          try {
            btn.focus();
          } catch (err) {}
        }
      }
    });

    function onMqChange() {
      closeAll();
    }

    if (mq.addEventListener) {
      mq.addEventListener("change", onMqChange);
    } else {
      mq.addListener(onMqChange);
    }
  });
})();
