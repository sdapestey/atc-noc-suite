/* Calendario Flatpickr compartido — Estadísticas / Cortes de Rama */
(function (global) {
  function fpMonthNames(fp) {
    const loc = fp.l10n || (flatpickr.l10ns && flatpickr.l10ns.es) || {};
    return (loc.months && loc.months.longhand) || flatpickr.l10ns.default.months.longhand;
  }

  function fpTodayParts() {
    const t = new Date();
    return { y: t.getFullYear(), m: t.getMonth() };
  }

  function fpMaxDateToday() {
    const t = new Date();
    t.setHours(23, 59, 59, 999);
    return t;
  }

  function fpIsMonthDisabled(monthIdx, year) {
    const { y, m } = fpTodayParts();
    if (year > y) return true;
    if (year === y && monthIdx > m) return true;
    return false;
  }

  function fpIsYearDisabled(year) {
    return year > fpTodayParts().y;
  }

  function fpYearBounds(fp) {
    let minY = fp.currentYear - 8;
    let maxY = fpTodayParts().y;
    const minD = fp.config.minDate;
    const maxD = fp.config.maxDate;
    if (minD instanceof Date) {
      minY = minD.getFullYear();
    }
    if (maxD instanceof Date) {
      maxY = Math.min(maxD.getFullYear(), maxY);
    }
    return { minY, maxY };
  }

  function applyFpMonthDisabled(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    cal.querySelectorAll(".noc-fp-month-grid .noc-fp-picker-opt").forEach((btn) => {
      const idx = Number(btn.dataset.month);
      const disabled = fpIsMonthDisabled(idx, fp.currentYear);
      btn.disabled = disabled;
      btn.classList.toggle("is-disabled", disabled);
      btn.setAttribute("aria-disabled", disabled ? "true" : "false");
    });
  }

  function closeFpPickerPanel(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    const panel = cal.querySelector(".noc-fp-picker-panel");
    if (panel) panel.hidden = true;
    cal.querySelectorAll(".noc-fp-chip.is-open").forEach((el) => el.classList.remove("is-open"));
  }

  function highlightFpMonthYear(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    cal.querySelectorAll(".noc-fp-month-grid .noc-fp-picker-opt").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.month) === fp.currentMonth);
    });
    cal.querySelectorAll(".noc-fp-year-grid .noc-fp-picker-opt").forEach((btn) => {
      const y = Number(btn.textContent);
      btn.classList.toggle("is-active", y === fp.currentYear);
      const disabled = fpIsYearDisabled(y);
      btn.disabled = disabled;
      btn.classList.toggle("is-disabled", disabled);
    });
    applyFpMonthDisabled(fp);
  }

  function syncFpMonthYearTriggers(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    const monthBtn = cal.querySelector(".noc-fp-month-trigger");
    const yearBtn = cal.querySelector(".noc-fp-year-trigger");
    if (!monthBtn || !yearBtn) return;
    const months = fpMonthNames(fp);
    monthBtn.textContent = months[fp.currentMonth] || "";
    yearBtn.textContent = String(fp.currentYear);
    highlightFpMonthYear(fp);
  }

  function renderFpYearGrid(fp, yearGrid) {
    yearGrid.innerHTML = "";
    const { minY, maxY } = fpYearBounds(fp);
    for (let y = maxY; y >= minY; y -= 1) {
      if (fpIsYearDisabled(y)) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "noc-fp-picker-opt";
      btn.textContent = String(y);
      btn.setAttribute("role", "option");
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (fpIsYearDisabled(y)) return;
        fp.changeYear(y);
        closeFpPickerPanel(fp);
        syncFpMonthYearTriggers(fp);
      });
      yearGrid.appendChild(btn);
    }
    highlightFpMonthYear(fp);
  }

  function enhanceFpMonthYear(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;

    if (cal.dataset.nocFpEnhanced !== "1") {
      cal.dataset.nocFpEnhanced = "1";
      const currentMonth = cal.querySelector(".flatpickr-current-month");
      if (!currentMonth) return;

      currentMonth
        .querySelectorAll(".flatpickr-monthDropdown-months, .numInput.cur-year, .cur-month")
        .forEach((el) => {
          el.style.display = "none";
          el.setAttribute("aria-hidden", "true");
        });

      const row = document.createElement("div");
      row.className = "noc-fp-current-row";

      const monthBtn = document.createElement("button");
      monthBtn.type = "button";
      monthBtn.className = "noc-fp-chip noc-fp-month-trigger";
      monthBtn.setAttribute("aria-haspopup", "listbox");

      const yearBtn = document.createElement("button");
      yearBtn.type = "button";
      yearBtn.className = "noc-fp-chip noc-fp-year-trigger";
      yearBtn.setAttribute("aria-haspopup", "listbox");

      row.append(monthBtn, yearBtn);
      currentMonth.appendChild(row);

      const panel = document.createElement("div");
      panel.className = "noc-fp-picker-panel";
      panel.hidden = true;

      const monthGrid = document.createElement("div");
      monthGrid.className = "noc-fp-month-grid";
      monthGrid.setAttribute("role", "listbox");

      const yearGrid = document.createElement("div");
      yearGrid.className = "noc-fp-year-grid";
      yearGrid.hidden = true;
      yearGrid.setAttribute("role", "listbox");

      panel.append(monthGrid, yearGrid);
      cal.querySelector(".flatpickr-months")?.appendChild(panel);

      fpMonthNames(fp).forEach((label, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "noc-fp-picker-opt";
        btn.textContent = label;
        btn.dataset.month = String(idx);
        btn.setAttribute("role", "option");
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (fpIsMonthDisabled(idx, fp.currentYear)) return;
          fp.changeMonth(idx, false);
          closeFpPickerPanel(fp);
          syncFpMonthYearTriggers(fp);
        });
        monthGrid.appendChild(btn);
      });

      monthBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const panelEl = cal.querySelector(".noc-fp-picker-panel");
        const monthEl = cal.querySelector(".noc-fp-month-grid");
        const yearEl = cal.querySelector(".noc-fp-year-grid");
        if (!panelEl || !monthEl || !yearEl) return;
        const showingMonth = !panelEl.hidden && !monthEl.hidden;
        if (showingMonth) {
          closeFpPickerPanel(fp);
          return;
        }
        panelEl.hidden = false;
        monthEl.hidden = false;
        yearEl.hidden = true;
        monthBtn.classList.add("is-open");
        yearBtn.classList.remove("is-open");
        highlightFpMonthYear(fp);
        applyFpMonthDisabled(fp);
      });

      yearBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const panelEl = cal.querySelector(".noc-fp-picker-panel");
        const monthEl = cal.querySelector(".noc-fp-month-grid");
        const yearEl = cal.querySelector(".noc-fp-year-grid");
        if (!panelEl || !monthEl || !yearEl) return;
        const showingYear = !panelEl.hidden && !yearEl.hidden;
        if (showingYear) {
          closeFpPickerPanel(fp);
          return;
        }
        renderFpYearGrid(fp, yearEl);
        panelEl.hidden = false;
        monthEl.hidden = true;
        yearEl.hidden = false;
        yearBtn.classList.add("is-open");
        monthBtn.classList.remove("is-open");
      });

      cal.addEventListener("mousedown", (ev) => ev.stopPropagation());
    }

    syncFpMonthYearTriggers(fp);
  }

  function bindFpHandlers(fp) {
    const prevOnMonthChange = fp.config.onMonthChange || [];
    const prevOnYearChange = fp.config.onYearChange || [];
    const prevOnOpen = fp.config.onOpen || [];
    const prevOnClose = fp.config.onClose || [];
    const prevOnReady = fp.config.onReady || [];

    fp.config.onMonthChange = [].concat(prevOnMonthChange, function () {
      syncFpMonthYearTriggers(fp);
      applyFpMonthDisabled(fp);
    });
    fp.config.onYearChange = [].concat(prevOnYearChange, function () {
      syncFpMonthYearTriggers(fp);
      applyFpMonthDisabled(fp);
    });
    fp.config.onOpen = [].concat(prevOnOpen, function () {
      enhanceFpMonthYear(fp);
      closeFpPickerPanel(fp);
    });
    fp.config.onClose = [].concat(prevOnClose, function () {
      closeFpPickerPanel(fp);
    });
    fp.config.onReady = [].concat(prevOnReady, function (_selected, _str, instance) {
      instance.calendarContainer.classList.add("noc-estadisticas-cal");
      if (instance.altInput) {
        instance.altInput.classList.add("noc-estadisticas-fecha-visible");
      }
      enhanceFpMonthYear(instance);
    });
  }

  function create(input, options) {
    options = options || {};
    if (!input || typeof flatpickr === "undefined") {
      return null;
    }
    const locale =
      flatpickr.l10ns && flatpickr.l10ns.es ? flatpickr.l10ns.es : flatpickr.l10ns.default;
    const fp = flatpickr(input, {
      locale,
      dateFormat: "Y-m-d",
      altInput: true,
      altFormat: "j \\d\\e F \\d\\e Y",
      allowInput: false,
      disableMobile: true,
      clickOpens: true,
      monthSelectorType: "static",
      defaultDate: options.defaultDate || input.value || undefined,
      minDate: options.minDate,
      maxDate: options.maxDate !== undefined ? options.maxDate : fpMaxDateToday(),
      onChange: options.onChange,
    });
    bindFpHandlers(fp);
    if (fp.calendarContainer) {
      fp.calendarContainer.classList.add("noc-estadisticas-cal");
    }
    if (fp.altInput) {
      fp.altInput.classList.add("noc-estadisticas-fecha-visible");
    }
    return fp;
  }

  function getIsoValue(fp) {
    return fp?.input?.value || "";
  }

  global.NocEstadisticasFlatpickr = {
    create,
    getIsoValue,
    maxDateToday: fpMaxDateToday,
    syncMonthYear: syncFpMonthYearTriggers,
  };
})(typeof window !== "undefined" ? window : globalThis);
