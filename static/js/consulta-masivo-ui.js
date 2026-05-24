/**
 * Consulta masiva: paginación, colapso y resaltado RAMA con todos los AID en DOWN.
 */
(function () {
  "use strict";

  var pageSize = 10;
  var currentPage = 0;
  var potenciasScheduled = new WeakSet();
  /** Mostrar paginador solo si hay más de 10 RAMAs (11+). */
  var PAGER_SHOW_ABOVE = 10;

  function potenciasParallelMax() {
    var cfg = window.__CONSULTA_INDEX_CFG__ || {};
    var n = parseInt(cfg.potenciasParallelMax, 10);
    return Number.isFinite(n) && n > 0 ? n : 32;
  }

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

  function pagerEl() {
    return document.getElementById("consulta-masivo-pager");
  }

  function syncPagerVisibility() {
    var pager = pagerEl();
    if (!pager) return;
    var show = sections().length > PAGER_SHOW_ABOVE;
    pager.hidden = !show;
  }

  function updatePagerUi() {
    syncPagerVisibility();
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

  function applyPage(opts) {
    opts = opts || {};
    var start = currentPage * pageSize;
    var end = start + pageSize;
    sections().forEach(function (sec, i) {
      var onPage = i >= start && i < end;
      sec.classList.toggle("consulta-section--page-hidden", !onPage);
      sec.hidden = !onPage;
    });
    updatePagerUi();
    if (!opts.skipPotencias) schedulePotenciasForVisible();
  }

  function sectionPotenciasAlreadyLoaded(sec) {
    if (typeof window._consultaSectionPotenciasPendientes === "function") {
      return !window._consultaSectionPotenciasPendientes(sec);
    }
    return potenciasScheduled.has(sec);
  }

  function markPotenciasScheduled(sec) {
    if (sec) potenciasScheduled.add(sec);
  }

  function setPage(p, opts) {
    opts = opts || {};
    var tp = totalPages();
    if (!tp) return;
    var next = Math.max(0, Math.min(p, tp - 1));
    if (next === currentPage && !opts.force) return;
    currentPage = next;
    applyPage(opts);
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
    var targetPage = Math.floor(i / pageSize);
    if (targetPage !== currentPage) setPage(targetPage);
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

  function classifyRamaRxStatus(section) {
    var pending = 0;
    var checked = 0;
    var downCount = 0;
    if (!section) return { pending: 0, checked: 0, downCount: 0 };

    var rows = section.querySelectorAll("tr[data-aid][data-fat-status]");
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
    return { pending: pending, checked: checked, downCount: downCount };
  }

  function ramaSections() {
    return sections().filter(function (sec) {
      return sec.getAttribute("data-es-rama") === "1";
    });
  }

  function updateRamaSummary() {
    var totalEl = document.getElementById("consulta-masivo-ramas-total");
    var upEl = document.getElementById("consulta-masivo-ramas-up");
    var downEl = document.getElementById("consulta-masivo-ramas-down");
    if (!totalEl || !upEl || !downEl) return;

    var ramas = ramaSections();
    var up = 0;
    var down = 0;
    ramas.forEach(function (sec) {
      var s = classifyRamaRxStatus(sec);
      if (s.pending > 0) return;
      if (s.checked === 0) return;
      if (s.checked === s.downCount) down += 1;
      else up += 1;
    });

    totalEl.textContent = String(ramas.length);
    upEl.textContent = String(up);
    downEl.textContent = String(down);
  }

  function evalRamaAllDown(section) {
    if (!section || !section.classList.contains("consulta-section--multi")) return;
    var panel = section.querySelector(".consulta-panel");
    if (!panel) return;

    var s = classifyRamaRxStatus(section);
    if (s.pending > 0) {
      updateRamaSummary();
      return;
    }
    if (s.checked > 0 && s.checked === s.downCount) {
      panel.classList.add("consulta-panel--all-down");
    } else {
      panel.classList.remove("consulta-panel--all-down");
    }
    updateRamaSummary();
  }

  function schedulePotenciasForVisible() {
    if (typeof window.cargarPotenciasSeccion !== "function") return;
    var entries = potenciaEntriesForVisible();
    if (!entries.length) return;
    var run =
      entries.length >= 2 && typeof window._consultaCargarPotenciasEntries === "function"
        ? window._consultaCargarPotenciasEntries(entries)
        : Promise.all(
            entries.map(function (e) {
              return window.cargarPotenciasSeccion(e.token, e.root).then(function () {
                evalRamaAllDown(e.root);
              });
            })
          );
    if (!run || !run.then) return;
    run.catch(function () {});
  }

  function potenciaEntriesForVisible() {
    if (typeof window.cargarPotenciasSeccion !== "function") return [];
    var entries = [];
    sections().forEach(function (sec) {
      if (sec.hidden || sec.classList.contains("consulta-section--page-hidden")) return;
      var token = (sec.getAttribute("data-query-token") || "").trim();
      if (!token) return;
      if (sectionPotenciasAlreadyLoaded(sec)) return;
      markPotenciasScheduled(sec);
      entries.push({ token: token, root: sec });
    });
    return entries;
  }

  function potenciaJobFnsForVisible() {
    return potenciaEntriesForVisible().map(function (e) {
      return function () {
        return window.cargarPotenciasSeccion(e.token, e.root).then(function () {
          evalRamaAllDown(e.root);
        });
      };
    });
  }

  function setQuicknavActive(idx) {
    document.querySelectorAll(".consulta-quicknav__a").forEach(function (a) {
      var href = a.getAttribute("href") || "";
      var m = href.match(/^#consulta-s(\d+)$/);
      var on = m && parseInt(m[1], 10) === idx;
      a.classList.toggle("consulta-quicknav__a--active", on);
      if (on) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    });
  }

  function bindQuicknav() {
    document.querySelectorAll(".consulta-quicknav__a").forEach(function (a) {
      if (a.dataset.consultaQuicknavBound === "1") return;
      a.dataset.consultaQuicknavBound = "1";
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href") || "";
        var m = href.match(/^#consulta-s(\d+)$/);
        if (!m) return;
        e.preventDefault();
        var idx = parseInt(m[1], 10);
        setQuicknavActive(idx);
        goToSectionIndex(idx);
      });
    });
  }

  function initPager(opts) {
    opts = opts || {};
    var sel = sizeSelect();
    if (!sel) return;
    pageSize = parseInt(sel.value, 10) || 10;
    currentPage = 0;
    sections().forEach(function (sec, i) {
      sec.setAttribute("data-masivo-index", String(i));
    });
    applyPage({ skipPotencias: Boolean(opts.skipPotencias) });
    bindQuicknav();
    bindPanelExpandCtos();
    updateRamaSummary();

    if (sel.dataset.consultaPagerBound !== "1") {
      sel.dataset.consultaPagerBound = "1";
      sel.addEventListener("change", function () {
        pageSize = parseInt(sel.value, 10) || 10;
        currentPage = 0;
        applyPage();
      });
    }
    var prev = prevBtn();
    var next = nextBtn();
    if (prev && prev.dataset.consultaPagerBound !== "1") {
      prev.dataset.consultaPagerBound = "1";
      prev.addEventListener("click", function () {
        setPage(currentPage - 1);
      });
    }
    if (next && next.dataset.consultaPagerBound !== "1") {
      next.dataset.consultaPagerBound = "1";
      next.addEventListener("click", function () {
        setPage(currentPage + 1);
      });
    }
  }

  window.ConsultaMasivoUi = {
    initPager: initPager,
    evalRamaAllDown: evalRamaAllDown,
    updateRamaSummary: updateRamaSummary,
    markPotenciasScheduled: markPotenciasScheduled,
    potenciaJobFnsForVisible: potenciaJobFnsForVisible,
    goToSectionIndex: goToSectionIndex,
    expandRamaSection: expandRamaSection,
    flashSection: flashSection,
  };
})();
