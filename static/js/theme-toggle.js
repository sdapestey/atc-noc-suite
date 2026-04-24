/**
 * Theme toggle for NOC pages.
 * Priority: localStorage > prefers-color-scheme.
 */
(function () {
  function isTheme(value) {
    return value === "dark" || value === "light";
  }

  function getPreferredTheme() {
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  function getCurrentTheme() {
    var attr = document.documentElement.getAttribute("data-theme");
    if (isTheme(attr)) return attr;
    return getPreferredTheme();
  }

  function setTheme(theme) {
    var next = isTheme(theme) ? theme : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch (e) {}
    syncButtons(next);
  }

  function buttonLabel(theme) {
    return theme === "dark" ? "Modo: Dark" : "Modo: Light";
  }

  function syncButtons(theme) {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.textContent = buttonLabel(theme);
      btn.setAttribute("aria-label", theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
      btn.setAttribute("title", theme === "dark" ? "Cambiar a light mode" : "Cambiar a dark mode");
    });
  }

  function init() {
    var current = getCurrentTheme();
    syncButtons(current);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setTheme(getCurrentTheme() === "dark" ? "light" : "dark");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
