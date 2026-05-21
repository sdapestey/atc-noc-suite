/**
 * Expand/collapse suave en <details.consulta-panel> (Consulta, varias búsquedas).
 * beforetoggle + transición de altura y opacidad. Sin dependencias.
 */
(function () {
  "use strict";

  var PANEL = "details.consulta-panel";
  var WRAP = ".consulta-panel__body-anim";
  var DUR = 0.3;
  var DURC = 0.26;
  var E = "cubic-bezier(0.2, 0.8, 0.2, 1)";

  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
  } catch (e) {
    return;
  }

  function getWrap(d) {
    return d.querySelector(WRAP);
  }

  function clearW(w) {
    if (!w) return;
    w.style.removeProperty("height");
    w.style.removeProperty("opacity");
    w.style.removeProperty("overflow");
    w.style.removeProperty("transition");
  }

  function openAnim(d) {
    var w = getWrap(d);
    if (!w) {
      return;
    }
    w.style.overflow = "hidden";
    w.style.height = "0px";
    w.style.opacity = "0";
    w.style.transition = "none";
    w.offsetHeight;
    var h = w.scrollHeight;
    if (h < 1) h = 1;
    w.style.transition =
      "height " + DUR + "s " + E + ", opacity " + 0.24 + "s ease 0.03s";
    w.style.height = h + "px";
    w.style.opacity = "1";
    function done(ev) {
      if (ev.target !== w) return;
      if (ev.propertyName !== "height") return;
      w.removeEventListener("transitionend", done);
      clearW(w);
    }
    w.addEventListener("transitionend", done);
  }

  function closeAnim(d) {
    var w = getWrap(d);
    if (!w) {
      d.removeAttribute("open");
      return;
    }
    var h = w.getBoundingClientRect().height;
    if (h < 1) {
      h = w.scrollHeight;
    }
    w.style.height = h + "px";
    w.style.opacity = "1";
    w.style.overflow = "hidden";
    w.style.transition = "none";
    w.offsetHeight;
    w.style.transition =
      "height " + DURC + "s ease, opacity 0.2s ease";
    w.style.height = "0px";
    w.style.opacity = "0";
    var tid = setTimeout(function () {
      if (d.open) {
        d.removeAttribute("open");
        w.removeEventListener("transitionend", end);
        clearW(w);
      }
    }, 500);
    function end(ev) {
      if (ev.target !== w) return;
      if (ev.propertyName !== "height" && ev.propertyName !== "opacity") {
        return;
      }
      w.removeEventListener("transitionend", end);
      clearTimeout(tid);
      d.removeAttribute("open");
      setTimeout(function () {
        clearW(w);
      }, 0);
    }
    w.addEventListener("transitionend", end);
  }

  function onBefore(e) {
    if (!e.target || e.target.tagName.toLowerCase() !== "details") {
      return;
    }
    var d = e.target;
    if (!d.classList.contains("consulta-panel")) {
      return;
    }
    if (!e.isTrusted) {
      return;
    }
    e.preventDefault();
    if (e.newState === "open") {
      d.setAttribute("open", "");
      requestAnimationFrame(function () {
        openAnim(d);
      });
    } else {
      closeAnim(d);
    }
  }

  var list = document.querySelectorAll(PANEL);
  for (var i = 0; i < list.length; i++) {
    list[i].addEventListener("beforetoggle", onBefore);
  }
})();
