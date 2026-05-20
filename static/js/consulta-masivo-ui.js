/**
 * Consulta masiva: paginación, colapso y resaltado RAMA con todos los AID en DOWN.
 */
(function () {
  "use strict";

  var pageSize = 20;
  var currentPage = 0;
  var potenciasScheduled = new WeakSet();

  function sections() {
    return Array.prototype.slice.call(
      document.querySelectorAll(".consulta-section--multi")
    );
  }

  function totalPages() {
    var n = sections().length;
    return n ? Math.ceil(n / pageSize) : 0;
  }

  function pageInfoEl() {
    return document.getElementById("consulta-masivo-page-info");
  }

  function prevBtn() {
    return document.getElementById("consulta-masivo-page-prev");
  }

  function nextBtn() {
    return document.getElementById("consulta-masivo-page-next");
  }

  function sizeSelect() {
    return document.getElementById("consulta-masivo-page-size");
  }

  function updatePagerUi() {
    var tp = totalPages();
    var info = pageInfoEl();
    if (info) {
      info.textContent =
        tp === 0 ? "0 resultados" : "Página " + (currentPage + 1) + " de " + tp;
    }
    var prev = prevBtn();
    var next = nextBtn();
    if (prev) prev.disabled = currentPage <= 0;
    if (next) next.disabled = currentPage >= tp - 1;
  }

  function applyPage() {
    var start = currentPage * pageSize;
    var end = start + pageSize;
    sections().forEach(function (sec, i) {
      var onPage = i >= start && i < end;
      sec.classList.toggle("consulta-section--page-hidden", !onPage);
      sec.hidden = !onPage;
    });
    updatePagerUi();
    schedulePotenciasForVisible();
  }

  function setPage(p) {
    var tp = totalPages();
    if (!tp) return;
    currentPage = Math.max(0, Math.min(p, tp - 1));
    applyPage();
  }

  var NAV_FLASH_MS = 4500;

  function expandAllCtosInSection(sec) {
    if (!sec) return;
    sec.querySelectorAll("details.consulta-cto-panel").forEach(function (det) {
      det.open = true;
    });
  }

  function expandRamaSection(sec, opts) {
    if (!sec) return;
    opts = opts || {};
    var panel = sec.querySelector("details.consulta-panel");
    if (panel) panel.open = true;
    if (opts.expandCtos !== false) expandAllCtosInSection(sec);
  }

  function flashSection(sec) {
    if (!sec) return;
    sec.classList.remove("consulta-section--nav-flash");
    void sec.offsetWidth;
    sec.classList.add("consulta-section--nav-flash");
    if (sec.scrollIntoView) {
      sec.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    window.setTimeout(function () {
      sec.classList.remove("consulta-section--nav-flash");
    }, NAV_FLASH_MS);
  }

  function bindPanelExpandCtos() {
    sections().forEach(function (sec) {
      var panel = sec.querySelector("details.consulta-panel");
      if (!panel || panel.dataset.consultaExpandBound === "1") return;
      panel.dataset.consultaExpandBound = "1";
      panel.addEventListener("toggle", function () {
        if (panel.open) expandAllCtosInSection(sec);
      });
    });
  }

  function goToSectionIndex(idx) {
    var i = parseInt(idx, 10);
    if (!Number.isFinite(i) || i < 0) return;
    setPage(Math.floor(i / pageSize));
    var sec = document.querySelector(
      '.consulta-section--multi[data-masivo-index="' + i + '"]'
    );
    if (sec) {
      expandRamaSection(sec, { expandCtos: true });
      flashSection(sec);
    }
  }

  function filaTieneAidReal(tr) {
    if (typeof _filaTieneAidReal === "function") return _filaTieneAidReal(tr);
    var aid = (tr.getAttribute("data-aid") || "").trim();
    return Boolean(aid && aid !== "-");
  }

  function filaSaltaPotencias(tr) {
    if (typeof _filaSaltaPotencias === "function") return _filaSaltaPotencias(tr);
    var st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
    return st === "FREE" || st === "RESERVED";
  }

  function evalRamaAllDown(section) {
    if (!section || !section.classList.contains("consulta-section--multi")) return;
    var panel = section.querySelector(".consulta-panel");
    if (!panel) return;

    var rows = section.querySelectorAll("tr[data-aid][data-fat-status]");
    var pending = 0;
    var checked = 0;
    var downCount = 0;

    rows.forEach(function (tr) {
      var st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
      if (st !== "IN SERVICE") return;
      if (!filaTieneAidReal(tr)) return;
      if (filaSaltaPotencias(tr)) return;

      var rxEl = tr.querySelector("td[id*='-rx-']");
      if (!rxEl || rxEl.classList.contains("consulta-potencia-loading")) {
        pending += 1;
        return;
      }
      checked += 1;
      var down =
        rxEl.classList.contains("status-down") ||
        String(rxEl.textContent || "")
          .trim()
          .toUpperCase() === "DOWN";
      if (down) downCount += 1;
    });

    if (pending > 0) return;
    if (checked > 0 && checked === downCount) {
      panel.classList.add("consulta-panel--all-down");
    } else {
      panel.classList.remove("consulta-panel--all-down");
    }
  }

  function schedulePotenciasForVisible() {
    if (typeof cargarPotenciasSeccion !== "function") return;
    sections().forEach(function (sec) {
      if (sec.hidden || sec.classList.contains("consulta-section--page-hidden")) return;
      if (potenciasScheduled.has(sec)) return;
      var token = (sec.getAttribute("data-query-token") || "").trim();
      if (!token) return;
      potenciasScheduled.add(sec);
      cargarPotenciasSeccion(token, sec).then(function () {
        evalRamaAllDown(sec);
      });
    });
  }

  function potenciaJobFnsForVisible() {
    if (typeof cargarPotenciasSeccion !== "function") return [];
    var fns = [];
    sections().forEach(function (sec) {
      if (sec.hidden || sec.classList.contains("consulta-section--page-hidden")) return;
      var token = (sec.getAttribute("data-query-token") || "").trim();
      if (!token) return;
      potenciasScheduled.add(sec);
      fns.push(function () {
        return cargarPotenciasSeccion(token, sec).then(function () {
          evalRamaAllDown(sec);
        });
      });
    });
    return fns;
  }

  function bindQuicknav() {
    document.querySelectorAll(".consulta-quicknav__a").forEach(function (a) {
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href") || "";
        var m = href.match(/^#consulta-s(\d+)$/);
        if (!m) return;
        e.preventDefault();
        goToSectionIndex(parseInt(m[1], 10));
      });
    });
  }

  function initPager() {
    var sel = sizeSelect();
    if (!sel) return;
    pageSize = parseInt(sel.value, 10) || 20;
    currentPage = 0;
    sections().forEach(function (sec, i) {
      sec.setAttribute("data-masivo-index", String(i));
    });
    applyPage();
    bindQuicknav();
    bindPanelExpandCtos();

    sel.addEventListener("change", function () {
      pageSize = parseInt(sel.value, 10) || 20;
      currentPage = 0;
      applyPage();
    });
    var prev = prevBtn();
    var next = nextBtn();
    if (prev) {
      prev.addEventListener("click", function () {
        setPage(currentPage - 1);
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        setPage(currentPage + 1);
      });
    }
  }

  window.ConsultaMasivoUi = {
    initPager: initPager,
    evalRamaAllDown: evalRamaAllDown,
    potenciaJobFnsForVisible: potenciaJobFnsForVisible,
    goToSectionIndex: goToSectionIndex,
    expandRamaSection: expandRamaSection,
    flashSection: flashSection,
  };
})();
