/**
 * Acciones tasa-composite (BW + reinyección) en detalle consulta índice.
 */
(function () {
  "use strict";

  var wired = false;
  var confirmResolve = null;
  var hsiDialogCtx = null;
  var hsiSuggestTimers = { upstream: null, downstream: null };

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escAttr(s) {
    return escHtml(s).replace(/'/g, "&#39;");
  }

  function toast(msg, opts) {
    if (window.NocToast && window.NocToast.show) {
      window.NocToast.show("toast", msg, opts || {});
    }
  }

  var REINYECTION_TOAST_ID = "toast";

  function showReinyeccionProgress() {
    toast("Reinyectando tasa-composite: eliminando, recreando y verificando…", {
      variant: "info",
      durationMs: 0,
      dismissible: false,
      id: REINYECTION_TOAST_ID,
    });
  }

  function showReinyeccionOk(json) {
    var detail =
      json && json.message ? String(json.message).trim() : "Reinyección completada.";
    toast("OK · " + detail, {
      variant: "success",
      durationMs: 12000,
      dismissible: true,
      keepVisible: true,
      id: REINYECTION_TOAST_ID,
    });
  }

  function showReinyeccionError(msg) {
    toast(msg || "No se pudo reinyectar.", {
      variant: "error",
      durationMs: 14000,
      dismissible: true,
      id: REINYECTION_TOAST_ID,
    });
  }

  function apiPost(url, payload, opts) {
    opts = opts || {};
    var init = {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    };
    var timer = null;
    if (opts.timeoutMs > 0 && typeof AbortController !== "undefined") {
      var ac = new AbortController();
      init.signal = ac.signal;
      timer = setTimeout(function () {
        ac.abort();
      }, opts.timeoutMs);
    }
    return fetch(url, init)
      .then(function (r) {
        return r.json().then(function (payload) {
          return { status: r.status, payload: payload };
        });
      })
      .then(function (r) {
        if (r.status === 401) {
          window.location.reload();
          return null;
        }
        return r.payload || {};
      })
      .catch(function (err) {
        if (opts.timeoutMs > 0 && err && err.name === "AbortError") {
          return { ok: false, message: "La operación tardó demasiado (timeout del cliente)." };
        }
        throw err;
      })
      .finally(function () {
        if (timer) clearTimeout(timer);
      });
  }

  function mutationPayload(target, accessId, operator) {
    var p = { device_name: target || "", target: target || "" };
    if (accessId) p.by_id = String(accessId);
    p.scope = "vno";
    p.operator = operator || "TASA";
    p.intent_type = "tasa-composite";
    return p;
  }

  function iconSvg(kind) {
    if (kind === "sync") {
      return (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M21 12a9 9 0 1 1-2.64-6.36" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
        '<path d="M21 3v6h-6M3 12a9 9 0 1 1 2.64 6.36" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
        '<path d="M3 21v-6h6" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
        "</svg>"
      );
    }
    if (kind === "tasa-hsi") {
      return (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M4 20h16" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
        '<path d="M7 20v-5M11 20V8M15 20v-8M19 20V5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
        "</svg>"
      );
    }
    return (
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-1 0v11a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V7" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg>"
    );
  }

  function setBtnBusy(btn, on) {
    if (!btn) return;
    btn.classList.toggle("altiplano-busy-spin", !!on);
    btn.disabled = !!on;
    btn.setAttribute("aria-busy", on ? "true" : "false");
  }

  function reinyeccionBtn(actionsEl) {
    if (!actionsEl || !actionsEl.querySelector) return null;
    return actionsEl.querySelector('[data-consulta-index-tasa-act="reinyeccion"]');
  }

  function setReinyeccionInFlight(actionsEl, on, btn) {
    if (actionsEl) actionsEl._reinyeccionInFlight = !!on;
    setBtnBusy(btn || reinyeccionBtn(actionsEl), !!on);
  }

  function finishReinyeccionSuccess(actionsEl, json) {
    showReinyeccionOk(json);
    if (actionsEl) actionsEl._reinyeccionInFlight = false;
    setBtnBusy(reinyeccionBtn(actionsEl), false);
  }

  function finishReinyeccionFailure(actionsEl, msg) {
    if (actionsEl) actionsEl._reinyeccionInFlight = false;
    showReinyeccionError(msg);
    setBtnBusy(reinyeccionBtn(actionsEl), false);
  }

  function finishReinyeccionCancelled(actionsEl) {
    if (actionsEl) actionsEl._reinyeccionInFlight = false;
    setBtnBusy(reinyeccionBtn(actionsEl), false);
  }

  function wireConfirm() {
    var dlg = document.getElementById("altiplano-confirm-dialog");
    var ok = document.getElementById("altiplano-confirm-ok");
    var cancel = document.getElementById("altiplano-confirm-cancel");
    if (!dlg || !ok || !cancel || dlg._consultaTasaConfirmWired) return;
    dlg._consultaTasaConfirmWired = true;
    function close(v) {
      if (dlg.open) dlg.close();
      if (confirmResolve) {
        var fn = confirmResolve;
        confirmResolve = null;
        fn(!!v);
      }
    }
    ok.addEventListener("click", function () {
      close(true);
    });
    cancel.addEventListener("click", function () {
      close(false);
    });
    dlg.addEventListener("cancel", function (e) {
      e.preventDefault();
      close(false);
    });
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg) close(false);
    });
  }

  function confirm(opts) {
    wireConfirm();
    var dlg = document.getElementById("altiplano-confirm-dialog");
    var titleEl = document.getElementById("altiplano-confirm-title");
    var msgEl = document.getElementById("altiplano-confirm-message");
    var listEl = document.getElementById("altiplano-confirm-list");
    var detailEl = document.getElementById("altiplano-confirm-detail");
    var ok = document.getElementById("altiplano-confirm-ok");
    var cancel = document.getElementById("altiplano-confirm-cancel");
    if (!dlg || !titleEl) {
      return Promise.resolve(window.confirm((opts.title || "") + "\n\n" + (opts.message || "")));
    }
    titleEl.textContent = opts.title || "¿Confirmar acción?";
    if (opts.message) {
      msgEl.hidden = false;
      msgEl.innerHTML = escHtml(opts.message).replace(/\n/g, "<br>");
    } else {
      msgEl.hidden = true;
      msgEl.textContent = "";
    }
    var items = Array.isArray(opts.items) ? opts.items : [];
    if (items.length) {
      listEl.hidden = false;
      listEl.innerHTML = items
        .map(function (it) {
          return "<li><code class=\"inline-code\">" + escHtml(String(it)) + "</code></li>";
        })
        .join("");
    } else {
      listEl.hidden = true;
      listEl.innerHTML = "";
    }
    if (opts.detail) {
      detailEl.hidden = false;
      detailEl.textContent = opts.detail;
    } else {
      detailEl.hidden = true;
      detailEl.textContent = "";
    }
    cancel.textContent = opts.cancelLabel || "Cancelar";
    ok.textContent = opts.confirmLabel || "Confirmar";
    ok.classList.toggle("altiplano-confirm-dialog-btn-ok--danger", opts.variant === "danger");
    return new Promise(function (resolve) {
      confirmResolve = resolve;
      dlg.showModal();
      ok.focus();
    });
  }

  function hsiFieldConfig(kind) {
    if (kind === "downstream") {
      return {
        input: "consulta-tasa-hsi-downstream",
        list: "consulta-tasa-hsi-downstream-suggest",
      };
    }
    return { input: "consulta-tasa-hsi-upstream", list: "consulta-tasa-hsi-upstream-suggest" };
  }

  function filterProfiles(profiles, kind) {
    return (profiles || []).filter(function (name) {
      var n = String(name || "").trim().toUpperCase();
      if (!n) return false;
      if (kind === "downstream") return n.indexOf("_DN") >= 0 || n.indexOf("TASA_SH") === 0;
      return n.indexOf("_UP") >= 0 || (n.indexOf("TASA_BW") === 0 && n.indexOf("_DN") < 0);
    });
  }

  function hideSuggest(listEl, inputEl) {
    if (!listEl) return;
    listEl.hidden = true;
    listEl.classList.remove("is-open");
    if (inputEl) inputEl.setAttribute("aria-expanded", "false");
  }

  function fillSuggestList(listId, profiles, inputEl, kind) {
    var ul = document.getElementById(listId);
    if (!ul) return;
    ul.innerHTML = "";
    var q = inputEl ? String(inputEl.value || "").trim().toLowerCase() : "";
    var items = filterProfiles(profiles, kind);
    var cur = inputEl ? String(inputEl.value || "").trim() : "";
    if (cur && items.indexOf(cur) < 0) items.unshift(cur);
    if (q) {
      items = items.filter(function (name) {
        return String(name).toLowerCase().indexOf(q) >= 0;
      });
    }
    if (!items.length) {
      var empty = document.createElement("li");
      empty.className = "altiplano-tasa-hsi-suggest__empty";
      empty.setAttribute("role", "presentation");
      empty.textContent = q ? "Sin coincidencias" : "Sin perfiles disponibles";
      ul.appendChild(empty);
    } else {
      items.slice(0, 100).forEach(function (name) {
        var li = document.createElement("li");
        li.className = "altiplano-tasa-hsi-suggest__item";
        li.setAttribute("role", "option");
        li.textContent = String(name);
        li.addEventListener("mousedown", function (ev) {
          ev.preventDefault();
          if (inputEl) {
            inputEl.value = String(name);
            inputEl.setAttribute("data-value", String(name));
          }
          hideSuggest(ul, inputEl);
        });
        ul.appendChild(li);
      });
    }
    var open = inputEl && document.activeElement === inputEl;
    ul.hidden = !open;
    ul.classList.toggle("is-open", !!open);
    if (inputEl) inputEl.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function hsiLiveFromInputs() {
    var upEl = document.getElementById("consulta-tasa-hsi-upstream");
    var dnEl = document.getElementById("consulta-tasa-hsi-downstream");
    var base =
      hsiDialogCtx && hsiDialogCtx.row && hsiDialogCtx.row.tasa_hsi
        ? Object.assign({}, hsiDialogCtx.row.tasa_hsi)
        : {};
    if (upEl && String(upEl.value || "").trim()) base.upstream_profile = String(upEl.value).trim();
    if (dnEl && String(dnEl.value || "").trim()) base.downstream_profile = String(dnEl.value).trim();
    return base;
  }

  function fetchHsiSuggestions(kind, query, done) {
    if (!hsiDialogCtx || !hsiDialogCtx.row || !hsiDialogCtx.row.target) {
      if (done) done([]);
      return;
    }
    apiPost("/dashboard/altiplano/tasa-composite-profile-suggestions", {
      kind: kind,
      target: hsiDialogCtx.row.target,
      operator: hsiDialogCtx.row.operator || "TASA",
      query: query || "",
      tasa_hsi: hsiLiveFromInputs(),
    })
      .then(function (out) {
        if (done) done(out && out.ok && out.profiles ? out.profiles : []);
      })
      .catch(function () {
        if (done) done([]);
      });
  }

  function updateHsiCurrentLabels(hsi) {
    var upCur = document.getElementById("consulta-tasa-hsi-upstream-current");
    var dnCur = document.getElementById("consulta-tasa-hsi-downstream-current");
    var data = hsi && typeof hsi === "object" ? hsi : {};
    var up = String(data.upstream_profile || "").trim();
    var dn = String(data.downstream_profile || "").trim();
    if (upCur) {
      upCur.innerHTML = up
        ? 'Implementado: <strong>' + escHtml(up) + "</strong>"
        : "Implementado: <span class=\"muted\">sin perfil informado</span>";
    }
    if (dnCur) {
      dnCur.innerHTML = dn
        ? 'Implementado: <strong>' + escHtml(dn) + "</strong>"
        : "Implementado: <span class=\"muted\">sin perfil informado</span>";
    }
  }

  function setHsiCurrentLoading(loading) {
    var upCur = document.getElementById("consulta-tasa-hsi-upstream-current");
    var dnCur = document.getElementById("consulta-tasa-hsi-downstream-current");
    if (!loading) return;
    var html = 'Implementado: <span class="muted">consultando…</span>';
    if (upCur) upCur.innerHTML = html;
    if (dnCur) dnCur.innerHTML = html;
  }

  function fetchTasaHsiCurrent(row, done) {
    if (!row || !row.target) {
      if (done) done(null);
      return;
    }
    var hsi = row.tasa_hsi && typeof row.tasa_hsi === "object" ? row.tasa_hsi : {};
    var hasUp = String(hsi.upstream_profile || "").trim();
    var hasDn = String(hsi.downstream_profile || "").trim();
    if (hasUp || hasDn) {
      if (done) done(hsi);
      return;
    }
    apiPost("/dashboard/altiplano/tasa-composite-hsi", {
      target: row.target,
      operator: row.operator || "TASA",
    })
      .then(function (out) {
        if (out && out.ok && out.tasa_hsi && typeof out.tasa_hsi === "object") {
          if (done) done(out.tasa_hsi);
          return;
        }
        if (done) done(null);
      })
      .catch(function () {
        if (done) done(null);
      });
  }

  function wireHsiInputs() {
    ["upstream", "downstream"].forEach(function (kind) {
      var cfg = hsiFieldConfig(kind);
      var el = document.getElementById(cfg.input);
      if (!el || el._consultaIndexTasaWired) return;
      el._consultaIndexTasaWired = true;
      el._tasaHsiProfiles = [];
      el.addEventListener("input", function () {
        var q = String(el.value || "").trim();
        el.setAttribute("data-value", q);
        if (hsiSuggestTimers[kind]) clearTimeout(hsiSuggestTimers[kind]);
        hsiSuggestTimers[kind] = setTimeout(function () {
          fetchHsiSuggestions(kind, q, function (profiles) {
            el._tasaHsiProfiles = profiles || [];
            fillSuggestList(cfg.list, profiles, el, kind);
          });
        }, 280);
      });
      el.addEventListener("focus", function () {
        fetchHsiSuggestions(kind, String(el.value || "").trim(), function (profiles) {
          el._tasaHsiProfiles = profiles || [];
          fillSuggestList(cfg.list, profiles, el, kind);
        });
      });
      el.addEventListener("blur", function () {
        setTimeout(function () {
          hideSuggest(document.getElementById(cfg.list), el);
        }, 160);
      });
    });
  }

  function wireHsiDialog() {
    var dlg = document.getElementById("consulta-tasa-hsi-dialog");
    if (!dlg || dlg._consultaIndexTasaWired) return;
    dlg._consultaIndexTasaWired = true;
    var cancelBtn = document.getElementById("consulta-tasa-hsi-dialog-cancel");
    var applyBtn = document.getElementById("consulta-tasa-hsi-dialog-apply");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        dlg.close();
        hsiDialogCtx = null;
      });
    }
    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        runHsiApply();
      });
    }
    dlg.addEventListener("cancel", function () {
      hsiDialogCtx = null;
    });
  }

  function openHsiDialog(row, btn) {
    var dlg = document.getElementById("consulta-tasa-hsi-dialog");
    var upEl = document.getElementById("consulta-tasa-hsi-upstream");
    var dnEl = document.getElementById("consulta-tasa-hsi-downstream");
    var tgtEl = document.getElementById("consulta-tasa-hsi-dialog-target");
    if (!dlg || !upEl || !dnEl) return;
    wireHsiInputs();
    hsiDialogCtx = { row: row || {}, btn: btn || null };
    var hsi = row && row.tasa_hsi && typeof row.tasa_hsi === "object" ? row.tasa_hsi : {};
    var needsFetch =
      !String(hsi.upstream_profile || "").trim() && !String(hsi.downstream_profile || "").trim();
    upEl.value = hsi.upstream_profile != null ? String(hsi.upstream_profile) : "";
    dnEl.value = hsi.downstream_profile != null ? String(hsi.downstream_profile) : "";
    if (needsFetch) setHsiCurrentLoading(true);
    else updateHsiCurrentLabels(hsi);
    if (tgtEl) tgtEl.textContent = row && row.target ? String(row.target) : "";
    if (typeof dlg.showModal === "function") dlg.showModal();
    fetchTasaHsiCurrent(row, function (fresh) {
      if (!hsiDialogCtx || !row || hsiDialogCtx.row.target !== row.target) return;
      if (fresh) {
        hsiDialogCtx.row.tasa_hsi = fresh;
        if (!String(upEl.value || "").trim() && fresh.upstream_profile) {
          upEl.value = String(fresh.upstream_profile);
        }
        if (!String(dnEl.value || "").trim() && fresh.downstream_profile) {
          dnEl.value = String(fresh.downstream_profile);
        }
        updateHsiCurrentLabels(fresh);
        var actionsEl = btn && btn.closest(".consulta-tasa-composite-actions");
        if (actionsEl && actionsEl._tasaRowCtx) actionsEl._tasaRowCtx.tasa_hsi = fresh;
      } else if (needsFetch) {
        updateHsiCurrentLabels(hsi);
      }
    });
    fetchHsiSuggestions("upstream", upEl.value, function (p) {
      upEl._tasaHsiProfiles = p || [];
    });
    fetchHsiSuggestions("downstream", dnEl.value, function (p) {
      dnEl._tasaHsiProfiles = p || [];
    });
  }

  function runHsiApply() {
    var dlg = document.getElementById("consulta-tasa-hsi-dialog");
    var upEl = document.getElementById("consulta-tasa-hsi-upstream");
    var dnEl = document.getElementById("consulta-tasa-hsi-downstream");
    var ctx = hsiDialogCtx;
    if (!ctx || !upEl || !dnEl) return;
    var target = ctx.row && ctx.row.target ? String(ctx.row.target) : "";
    var upstream = String(upEl.value || "").trim();
    var downstream = String(dnEl.value || "").trim();
    var operator = ctx.row.operator || "TASA";
    var accessId = ctx.row.access_id || "";
    var btn = ctx.btn;
    var row = ctx.row;
    if (!target) return;
    if (!upstream || !downstream) {
      toast("Completá Traffic Descriptor y Shaper Profile.", { variant: "warning" });
      return;
    }
    if (!window.runConsultaAltiplanoAction) {
      toast("Diálogo de autenticación no disponible", { variant: "error" });
      return;
    }
    var payloadBase = mutationPayload(target, accessId, operator);
    payloadBase.tasa_hsi = {
      upstream_profile: upstream,
      downstream_profile: downstream,
    };
    if (dlg && typeof dlg.close === "function") dlg.close();
    hsiDialogCtx = null;

    runConsultaAltiplanoAction({
      dialog: {
        title: "Modificar perfiles HSI",
        message:
          "¿Confirmás actualizar Traffic Descriptor y Shaper en\n" + target + "?",
        okLabel: "Aplicar perfiles",
      },
      execute: function () {
        return apiPost("/dashboard/altiplano/actualizar-tasa-composite-profiles", payloadBase).then(
          function (out) {
            return {
              ok: !!(out && out.ok),
              status: out && out.ok ? 200 : 502,
              json: out || {},
            };
          }
        );
      },
      onCommitStart: function () {
        setBtnBusy(btn, true);
      },
      onSuccess: function (json) {
        var nextHsi = {
          upstream_profile: upstream,
          downstream_profile: downstream,
        };
        if (row) row.tasa_hsi = nextHsi;
        var actionsEl = btn && btn.closest(".consulta-tasa-composite-actions");
        if (actionsEl && actionsEl._tasaRowCtx) actionsEl._tasaRowCtx.tasa_hsi = nextHsi;
        toast(json.message || "Perfiles HSI actualizados.", { variant: "success" });
      },
      onFinally: function () {
        setBtnBusy(btn, false);
      },
    }).catch(function (err) {
      if (err && err.message === "cancelled") return;
      if (err && err.authError) return;
      toast(err.message || "No se pudieron modificar los perfiles HSI.", { variant: "error" });
    });
  }

  function rowFromActionsEl(actionsEl) {
    if (!actionsEl || !actionsEl._tasaRowCtx) {
      return { target: "", access_id: "", operator: "TASA", tasa_hsi: null, intent_type: "tasa-composite" };
    }
    return Object.assign({}, actionsEl._tasaRowCtx);
  }

  function renderReinyeccionBtn(row) {
    var tgt = row.target || "";
    var aid = row.access_id || "";
    var op = row.operator || "TASA";
    var extra =
      ' data-consulta-index-tasa-scope="vno" data-operator="' +
      escAttr(op) +
      '" data-intent-type="tasa-composite" data-target="' +
      escAttr(tgt) +
      '"' +
      (aid ? ' data-access-id="' + escAttr(aid) + '"' : "");
    return (
      '<button type="button" class="altiplano-consulta-act-btn" data-consulta-index-tasa-act="reinyeccion"' +
      extra +
      ' title="Reinyectar tasa-composite (borra y recrea HSI con los mismos perfiles)">' +
      iconSvg("del") +
      "</button>"
    );
  }

  function mount(container, opts) {
    if (!container) return;
    opts = opts || {};
    var target = String(opts.target || "").trim();
    if (!target) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }
    container.hidden = false;
    container._tasaRowCtx = {
      target: target,
      access_id: String(opts.accessId || "").trim(),
      operator: String(opts.operator || "TASA").trim().toUpperCase() || "TASA",
      tasa_hsi:
        opts.tasaHsi && typeof opts.tasaHsi === "object" ? Object.assign({}, opts.tasaHsi) : null,
      intent_type: "tasa-composite",
    };
    if (container._reinyeccionInFlight) return;
    var extra =
      ' data-consulta-index-tasa-scope="vno" data-operator="' +
      escAttr(container._tasaRowCtx.operator) +
      '" data-intent-type="tasa-composite" data-target="' +
      escAttr(target) +
      '"' +
      (container._tasaRowCtx.access_id
        ? ' data-access-id="' + escAttr(container._tasaRowCtx.access_id) + '"'
        : "");
    container.innerHTML =
      '<div class="altiplano-consulta-act-strip consulta-index-tasa-actions">' +
      '<button type="button" class="altiplano-consulta-act-btn" data-consulta-index-tasa-act="tasa-hsi"' +
      extra +
      ' title="Perfiles de ancho de banda (Traffic Descriptor y Shaper)">' +
      iconSvg("tasa-hsi") +
      "</button>" +
      renderReinyeccionBtn(container._tasaRowCtx) +
      "</div>";
  }

  function handleClick(ev) {
    var btn = ev.target.closest("[data-consulta-index-tasa-act]");
    if (!btn || btn.disabled) return;
    var actionsEl = btn.closest(".consulta-tasa-composite-actions");
    if (!btn.closest(".consulta-index-tasa-actions") && !actionsEl) return;
    ev.preventDefault();
    var act = btn.getAttribute("data-consulta-index-tasa-act");
    var row = rowFromActionsEl(actionsEl);
    var target = row.target || btn.getAttribute("data-target") || "";
    var accessId = row.access_id || btn.getAttribute("data-access-id") || "";
    var operator = row.operator || btn.getAttribute("data-operator") || "TASA";

    if (act === "tasa-hsi") {
      openHsiDialog(row, btn);
      return;
    }

    if (!target || act !== "reinyeccion") return;

    if (!window.runConsultaAltiplanoAction) {
      toast("Diálogo de autenticación no disponible", { variant: "error" });
      return;
    }

    var payloadBase = mutationPayload(target, accessId, operator);
    if (row.tasa_hsi) payloadBase.tasa_hsi = row.tasa_hsi;

    runConsultaAltiplanoAction({
      dialog: {
        title: "¿Reinyectar tasa-composite?",
        message:
          "En " +
          operator +
          " se borrará y volverá a crear:\n" +
          target +
          "\n\n1) Eliminar intent tasa-composite\n2) Create Services con los mismos perfiles HSI",
        danger: true,
        okLabel: "Reinyectar",
        loadingOkLabel: "Reinyectando…",
        loadingMessage: "Reinyectando tasa-composite en " + operator + "…",
      },
      execute: function () {
        return apiPost("/dashboard/altiplano/reinyectar-tasa-composite", payloadBase, {
          timeoutMs: 360000,
        }).then(function (out) {
          return {
            ok: !!(out && out.ok),
            status: out && out.ok ? 200 : 502,
            json: out || {},
          };
        });
      },
      onCommitStart: function () {
        setReinyeccionInFlight(actionsEl, true, btn);
        showReinyeccionProgress();
      },
      onSuccess: function (json) {
        finishReinyeccionSuccess(actionsEl, json);
      },
    }).catch(function (err) {
      if (err && err.message === "cancelled") {
        finishReinyeccionCancelled(actionsEl);
        return;
      }
      if (err && err.authError) {
        finishReinyeccionCancelled(actionsEl);
        return;
      }
      finishReinyeccionFailure(actionsEl, err.message);
    });
  }

  function init() {
    if (wired) return;
    wired = true;
    wireConfirm();
    wireHsiDialog();
    document.addEventListener("click", handleClick);
  }

  window.ConsultaTasaCompositeActions = {
    init: init,
    mount: mount,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
