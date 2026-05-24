/**
 * Autenticación Altiplano en consulta índice: login, confirmación y cambio SN.
 */
(function () {
  "use strict";

  var CACHE_KEY = "atc_noc_consulta_altiplano_auth";
  var DEFAULT_CACHE_TTL_MS = 30 * 60 * 1000;

  function cacheTtlMs() {
    var cfg = window.__CONSULTA_INDEX_CFG__ || {};
    var sec = parseInt(cfg.altiplanoAuthCacheSeconds, 10);
    if (sec >= 60) return sec * 1000;
    return DEFAULT_CACHE_TTL_MS;
  }

  var wiredAuth = false;
  var wiredSn = false;
  var pendingResolve = null;
  var pendingReject = null;
  var pendingSubmit = null;
  var pendingOnCommitStart = null;
  var lastDialogOpts = null;
  var dialogLoading = false;

  var snPendingResolve = null;
  var snPendingReject = null;
  var snPendingSubmit = null;
  var snPendingOnCommitStart = null;
  var snDialogLoading = false;

  function el(id) {
    return document.getElementById(id);
  }

  function readCache() {
    try {
      var raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || !data.u || !data.p || !data.exp || Date.now() > data.exp) {
        sessionStorage.removeItem(CACHE_KEY);
        return null;
      }
      var pwd = "";
      try {
        pwd = decodeURIComponent(escape(atob(data.p)));
      } catch (_e) {
        sessionStorage.removeItem(CACHE_KEY);
        return null;
      }
      return { username: data.u, password: pwd, expiresAt: data.exp };
    } catch (_e2) {
      return null;
    }
  }

  function writeCache(username, password) {
    try {
      sessionStorage.setItem(
        CACHE_KEY,
        JSON.stringify({
          u: String(username || "").trim(),
          p: btoa(unescape(encodeURIComponent(String(password || "")))),
          exp: Date.now() + cacheTtlMs(),
        })
      );
    } catch (_e) {
      /* quota / private mode */
    }
  }

  function clearCache() {
    try {
      sessionStorage.removeItem(CACHE_KEY);
    } catch (_e) {
      /* ignore */
    }
  }

  function cacheMinutesLeft(expiresAt) {
    return Math.max(1, Math.ceil((expiresAt - Date.now()) / 60000));
  }

  function authErrorFromResult(result) {
    if (result.status === 401) {
      clearCache();
      var msg =
        (result.json && result.json.message) ||
        "Usuario o contraseña incorrectos. Verificá las credenciales de Altiplano.";
      return Object.assign(new Error(msg), { authError: true });
    }
    if (!result.ok || !result.json || !result.json.ok) {
      return new Error(
        (result.json && result.json.message) ||
          "No se pudo completar la operación en Altiplano."
      );
    }
    return null;
  }

  function validateAltiplanoLogin(creds, operador) {
    return fetch("/consulta/altiplano/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        altiplano_user: creds.username,
        altiplano_password: creds.password,
        operador: String(operador || "").trim(),
      }),
    }).then(function (res) {
      return res.json().then(function (json) {
        return { ok: res.ok, status: res.status, json: json || {} };
      });
    });
  }

  function setDialogLoading(on) {
    dialogLoading = Boolean(on);
    var dlg = el("consulta-altiplano-auth-dialog");
    var btnOk = el("consulta-altiplano-auth-ok");
    var btnCancel = el("consulta-altiplano-auth-cancel");
    var form = el("consulta-altiplano-auth-form");
    if (dlg) dlg.classList.toggle("consulta-altiplano-auth-dialog--loading", dialogLoading);
    if (btnOk) {
      btnOk.disabled = dialogLoading;
      btnOk.setAttribute("aria-busy", dialogLoading ? "true" : "false");
    }
    if (btnCancel) btnCancel.disabled = dialogLoading;
    if (form) {
      form.querySelectorAll("input").forEach(function (inp) {
        inp.disabled = dialogLoading;
      });
    }
  }

  function clearError() {
    var err = el("consulta-altiplano-auth-error");
    if (err) {
      err.hidden = true;
      err.textContent = "";
    }
  }

  function showError(msg) {
    var err = el("consulta-altiplano-auth-error");
    if (!err) return;
    err.textContent = msg || "Error";
    err.hidden = !msg;
  }

  function setSnFieldVisible(visible, opts) {
    var snWrap = el("consulta-altiplano-auth-sn-wrap");
    var snEl = el("consulta-altiplano-auth-sn");
    if (!snWrap) return;
    var show = visible === true;
    snWrap.hidden = !show;
    snWrap.setAttribute("aria-hidden", show ? "false" : "true");
    snWrap.style.display = show ? "" : "none";
    if (snEl) {
      if (show) {
        snEl.value = opts && opts.snValue != null ? String(opts.snValue) : "";
        if (opts && opts.snPlaceholder) snEl.placeholder = opts.snPlaceholder;
        snEl.required = true;
      } else {
        snEl.value = "";
        snEl.required = false;
        snEl.removeAttribute("aria-invalid");
      }
    }
  }

  function setCredsVisible(visible) {
    var credsWrap = el("consulta-altiplano-auth-creds-wrap");
    if (!credsWrap) return;
    var show = visible === true;
    credsWrap.hidden = !show;
    credsWrap.setAttribute("aria-hidden", show ? "false" : "true");
    credsWrap.style.display = show ? "" : "none";
  }

  function setSessionBar(cache, forceHidden) {
    var bar = el("consulta-altiplano-auth-session");
    var userTxt = el("consulta-altiplano-auth-session-user");
    var ttlTxt = el("consulta-altiplano-auth-session-ttl");
    if (!bar) return;
    if (forceHidden || !cache) {
      bar.hidden = true;
      bar.style.display = "none";
      setCredsVisible(true);
      return;
    }
    bar.hidden = false;
    bar.style.display = "";
    if (userTxt) userTxt.textContent = cache.username;
    if (ttlTxt) {
      ttlTxt.textContent =
        "Sesión activa · " + cacheMinutesLeft(cache.expiresAt) + " min restantes";
    }
    setCredsVisible(false);
  }

  function showCredentialsForm(prefill) {
    clearCache();
    setSessionBar(null, true);
    setSnFieldVisible(false);
    var userEl = el("consulta-altiplano-auth-user");
    var pwdEl = el("consulta-altiplano-auth-password");
    if (userEl) userEl.value = (prefill && prefill.username) || "";
    if (pwdEl) pwdEl.value = (prefill && prefill.password) || "";
    if (userEl) userEl.focus();
  }

  function closeDialog(result) {
    var dlg = el("consulta-altiplano-auth-dialog");
    setDialogLoading(false);
    setSnFieldVisible(false);
    if (dlg && dlg.open) dlg.close();
    var res = pendingResolve;
    var rej = pendingReject;
    pendingResolve = null;
    pendingReject = null;
    pendingSubmit = null;
    pendingOnCommitStart = null;
    if (result && res) res(result);
    else if (!result && rej) {
      rej(Object.assign(new Error("cancelled"), { name: "AbortError" }));
    }
  }

  function dismissDialog() {
    var dlg = el("consulta-altiplano-auth-dialog");
    setDialogLoading(false);
    if (dlg && dlg.open) dlg.close();
  }

  function finalizeSubmitSuccess(payload) {
    writeCache(payload.username, payload.password);
    var res = pendingResolve;
    pendingResolve = null;
    pendingReject = null;
    pendingSubmit = null;
    pendingOnCommitStart = null;
    if (res) res(payload);
  }

  function wireDialog() {
    if (wiredAuth) return;
    var dlg = el("consulta-altiplano-auth-dialog");
    if (!dlg) return;
    wiredAuth = true;

    var btnCancel = el("consulta-altiplano-auth-cancel");
    var btnOk = el("consulta-altiplano-auth-ok");
    var form = el("consulta-altiplano-auth-form");
    var btnSwitch = el("consulta-altiplano-auth-switch-user");

    if (btnCancel) {
      btnCancel.addEventListener("click", function () {
        if (dialogLoading) return;
        closeDialog(null);
      });
    }
    dlg.addEventListener("cancel", function (ev) {
      ev.preventDefault();
      if (dialogLoading) return;
      closeDialog(null);
    });
    dlg.addEventListener("close", function () {
      if (pendingSubmit) return;
      if (pendingResolve || pendingReject) closeDialog(null);
    });

    if (btnSwitch) {
      btnSwitch.addEventListener("click", function () {
        if (dialogLoading) return;
        showCredentialsForm(readCache() || {});
        clearError();
      });
    }

    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        submitFromForm();
      });
    }
    if (btnOk) {
      btnOk.addEventListener("click", function () {
        submitFromForm();
      });
    }
  }

  function collectCredentialsFromForm() {
    var userEl = el("consulta-altiplano-auth-user");
    var pwdEl = el("consulta-altiplano-auth-password");
    var cache = readCache();
    var confirmOnly =
      lastDialogOpts &&
      (lastDialogOpts.confirmOnly === true || lastDialogOpts.mode === "confirm");
    var useCached =
      cache &&
      (confirmOnly ||
        (el("consulta-altiplano-auth-creds-wrap") &&
          el("consulta-altiplano-auth-creds-wrap").hidden));

    var username = "";
    var password = "";
    if (useCached) {
      username = cache.username;
      password = cache.password;
    } else {
      username = userEl ? String(userEl.value || "").trim() : "";
      password = pwdEl ? String(pwdEl.value || "") : "";
      if (cache && !password) {
        username = cache.username;
        password = cache.password;
        useCached = true;
      }
    }

    if (!username || !password) {
      showError(
        confirmOnly
          ? "La sesión de Altiplano expiró. Volvé a ingresar."
          : "Completá usuario y contraseña de Altiplano."
      );
      if (!useCached) {
        if (!username && userEl) userEl.focus();
        else if (pwdEl) pwdEl.focus();
      }
      return null;
    }

    return { username: username, password: password };
  }

  function submitFromForm() {
    if (dialogLoading) return;
    var payload = collectCredentialsFromForm();
    if (!payload) return;
    clearError();
    if (pendingSubmit) {
      var submitFn = pendingSubmit;
      var commitStart = pendingOnCommitStart;
      setDialogLoading(true);
      submitFn(payload)
        .then(function () {
          if (commitStart) commitStart(payload);
          dismissDialog();
          finalizeSubmitSuccess(payload);
        })
        .catch(function (err) {
          setDialogLoading(false);
          if (err && err.authError) {
            showError(err.message);
            showCredentialsForm({ username: payload.username });
            return;
          }
          var rej = pendingReject;
          pendingResolve = null;
          pendingReject = null;
          pendingSubmit = null;
          pendingOnCommitStart = null;
          if (err && err.message === "cancelled") {
            if (rej) rej(err);
            return;
          }
          showError(err.message || "Error al validar en Altiplano.");
          if (rej) rej(err);
        });
      return;
    }
    closeDialog(payload);
  }

  function configureDialog(opts) {
    opts = opts || {};
    var dlg = el("consulta-altiplano-auth-dialog");
    var titleEl = el("consulta-altiplano-auth-title");
    var msgEl = el("consulta-altiplano-auth-message");
    var userEl = el("consulta-altiplano-auth-user");
    var pwdEl = el("consulta-altiplano-auth-password");
    var btnOk = el("consulta-altiplano-auth-ok");
    var cache = opts.useCache !== false ? readCache() : null;

    setSnFieldVisible(false);

    if (titleEl) titleEl.textContent = opts.title || "Confirmar en Altiplano";
    if (msgEl) {
      var msg = opts.message || "";
      msgEl.textContent = msg;
      msgEl.hidden = !msg;
    }
    if (btnOk) {
      btnOk.textContent = opts.okLabel || "Confirmar";
      btnOk.classList.toggle(
        "altiplano-confirm-dialog-btn-ok--danger",
        Boolean(opts.danger)
      );
    }
    if (dlg) {
      dlg.classList.toggle(
        "consulta-altiplano-auth-dialog--danger",
        Boolean(opts.danger)
      );
    }

    var confirmOnly = opts.confirmOnly === true || opts.mode === "confirm";
    if (confirmOnly) {
      setSessionBar(null, true);
      setCredsVisible(false);
    } else if (cache && !opts.forceCredentials) {
      setSessionBar(cache, false);
      if (userEl) userEl.value = cache.username;
      if (pwdEl) pwdEl.value = "";
    } else {
      setSessionBar(null, true);
      if (userEl) userEl.value = opts.prefillUser || "";
      if (pwdEl) pwdEl.value = "";
    }

    clearError();
    if (opts.initialError) showError(opts.initialError);
    setDialogLoading(false);
  }

  function openDialog(opts, onSubmit, onCommitStart) {
    wireDialog();
    var dlg = el("consulta-altiplano-auth-dialog");
    if (!dlg) {
      return Promise.reject(new Error("Diálogo de autenticación no disponible"));
    }
    lastDialogOpts = opts || {};
    configureDialog(opts);
    pendingSubmit = onSubmit || null;
    pendingOnCommitStart = onCommitStart || null;

    return new Promise(function (resolve, reject) {
      pendingResolve = resolve;
      pendingReject = reject;
      try {
        dlg.showModal();
      } catch (e) {
        reject(e);
        return;
      }
      var credsWrap = el("consulta-altiplano-auth-creds-wrap");
      if (credsWrap && !credsWrap.hidden) {
        var userEl = el("consulta-altiplano-auth-user");
        if (userEl) userEl.focus();
      }
    });
  }

  /**
   * Solo login Altiplano (valida contra NBI y cachea sesión).
   */
  function runConsultaAltiplanoLogin(opts) {
    opts = opts || {};
    var dialogOpts = Object.assign(
      {
        title: "Ingresar a Altiplano",
        message: "Usuario y contraseña de Altiplano para continuar.",
        okLabel: "Ingresar",
      },
      opts.dialog || {}
    );

    return openDialog(dialogOpts, function (creds) {
      return validateAltiplanoLogin(creds, opts.operador).then(function (result) {
        var err = authErrorFromResult(result);
        if (err) throw err;
        return creds;
      });
    }).catch(function (err) {
      if (err && err.message === "cancelled") return;
      throw err;
    });
  }

  function ensureConsultaAltiplanoSession(opts) {
    opts = opts || {};
    var cache = readCache();
    if (cache && !opts.forceCredentials) {
      return Promise.resolve(cache);
    }
    return runConsultaAltiplanoLogin(opts);
  }

  function setSnDialogLoading(on) {
    snDialogLoading = Boolean(on);
    var dlg = el("consulta-sn-change-dialog");
    var btnOk = el("consulta-sn-change-ok");
    var btnCancel = el("consulta-sn-change-cancel");
    var input = el("consulta-sn-change-input");
    if (dlg) dlg.classList.toggle("consulta-sn-change-dialog--loading", snDialogLoading);
    if (btnOk) {
      btnOk.disabled = snDialogLoading;
      btnOk.setAttribute("aria-busy", snDialogLoading ? "true" : "false");
    }
    if (btnCancel) btnCancel.disabled = snDialogLoading;
    if (input) input.disabled = snDialogLoading;
  }

  function clearSnError() {
    var err = el("consulta-sn-change-error");
    if (err) {
      err.hidden = true;
      err.textContent = "";
    }
  }

  function showSnError(msg) {
    var err = el("consulta-sn-change-error");
    if (!err) return;
    err.textContent = msg || "Error";
    err.hidden = !msg;
  }

  function validateSnValue(sn) {
    var v = String(sn || "").trim().toUpperCase();
    if (!v) return { ok: false, message: "Ingresá el nuevo SN." };
    if (v.length !== 12 && v.length !== 16) {
      return {
        ok: false,
        message:
          "SN inválido: usá 12 caracteres (ej. SDMC5C73B3AF) o los 16 hex del rótulo de la ONT.",
      };
    }
    return { ok: true, value: v };
  }

  function closeSnDialog(result) {
    var dlg = el("consulta-sn-change-dialog");
    setSnDialogLoading(false);
    if (dlg && dlg.open) dlg.close();
    var res = snPendingResolve;
    var rej = snPendingReject;
    snPendingResolve = null;
    snPendingReject = null;
    snPendingSubmit = null;
    snPendingOnCommitStart = null;
    if (result && res) res(result);
    else if (!result && rej) {
      rej(Object.assign(new Error("cancelled"), { name: "AbortError" }));
    }
  }

  function dismissSnDialog() {
    var dlg = el("consulta-sn-change-dialog");
    setSnDialogLoading(false);
    if (dlg && dlg.open) dlg.close();
  }

  function wireSnDialog() {
    if (wiredSn) return;
    var dlg = el("consulta-sn-change-dialog");
    if (!dlg) return;
    wiredSn = true;

    var btnCancel = el("consulta-sn-change-cancel");
    var btnOk = el("consulta-sn-change-ok");
    var input = el("consulta-sn-change-input");

    if (btnCancel) {
      btnCancel.addEventListener("click", function () {
        if (snDialogLoading) return;
        closeSnDialog(null);
      });
    }
    dlg.addEventListener("cancel", function (ev) {
      ev.preventDefault();
      if (snDialogLoading) return;
      closeSnDialog(null);
    });
    dlg.addEventListener("close", function () {
      if (snPendingSubmit) return;
      if (snPendingResolve || snPendingReject) closeSnDialog(null);
    });
    if (btnOk) {
      btnOk.addEventListener("click", function () {
        submitSnFromForm();
      });
    }
    if (input) {
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          submitSnFromForm();
        }
      });
    }
  }

  function submitSnFromForm() {
    if (snDialogLoading) return;
    var input = el("consulta-sn-change-input");
    var checked = validateSnValue(input ? input.value : "");
    if (!checked.ok) {
      showSnError(checked.message);
      if (input) input.focus();
      return;
    }
    clearSnError();
    var payload = { new_sn: checked.value };
    if (!snPendingSubmit) {
      closeSnDialog(payload);
      return;
    }
    var submitFn = snPendingSubmit;
    var commitStart = snPendingOnCommitStart;
    setSnDialogLoading(true);
    submitFn(payload)
      .then(function () {
        if (commitStart) commitStart(payload);
        dismissSnDialog();
        var res = snPendingResolve;
        snPendingResolve = null;
        snPendingReject = null;
        snPendingSubmit = null;
        snPendingOnCommitStart = null;
        if (res) res(payload);
      })
      .catch(function (err) {
        setSnDialogLoading(false);
        if (err && err.message === "cancelled") {
          var rej = snPendingReject;
          snPendingResolve = null;
          snPendingReject = null;
          snPendingSubmit = null;
          snPendingOnCommitStart = null;
          if (rej) rej(err);
          return;
        }
        showSnError(err.message || "No se pudo cambiar el SN.");
      });
  }

  function openSnChangeDialog(opts, onSubmit, onCommitStart) {
    wireSnDialog();
    var dlg = el("consulta-sn-change-dialog");
    if (!dlg) {
      return Promise.reject(new Error("Diálogo de cambio de SN no disponible"));
    }
    opts = opts || {};
    var titleEl = el("consulta-sn-change-title");
    var msgEl = el("consulta-sn-change-message");
    var currentEl = el("consulta-sn-change-current");
    var input = el("consulta-sn-change-input");
    var btnOk = el("consulta-sn-change-ok");

    if (titleEl) titleEl.textContent = opts.title || "Cambiar SN de la ONT";
    if (msgEl) {
      var msg = opts.message || "";
      msgEl.textContent = msg;
      msgEl.hidden = !msg;
    }
    if (currentEl) {
      var cur = opts.currentSn != null ? String(opts.currentSn).trim() : "";
      currentEl.textContent = cur || "—";
    }
    if (input) {
      input.value = opts.snValue != null ? String(opts.snValue) : "";
      if (opts.snPlaceholder) input.placeholder = opts.snPlaceholder;
    }
    if (btnOk) btnOk.textContent = opts.okLabel || "Cambiar SN";

    clearSnError();
    setSnDialogLoading(false);
    snPendingSubmit = onSubmit || null;
    snPendingOnCommitStart = onCommitStart || null;

    return new Promise(function (resolve, reject) {
      snPendingResolve = resolve;
      snPendingReject = reject;
      try {
        dlg.showModal();
      } catch (e) {
        reject(e);
        return;
      }
      if (input) {
        input.focus();
        input.select();
      }
    });
  }

  /**
   * Segundo paso: popup solo con el nuevo SN (requiere creds ya validadas).
   */
  function runConsultaSnChange(opts) {
    opts = opts || {};
    var creds = opts.creds;
    if (!creds || !creds.username || !creds.password) {
      return Promise.reject(new Error("Sesión Altiplano no disponible"));
    }

    function handleResult(result) {
      var err = authErrorFromResult(result);
      if (err) throw err;
      writeCache(creds.username, creds.password);
      if (opts.onSuccess) opts.onSuccess(result.json, creds);
    }

    return openSnChangeDialog(
      opts.dialog || {},
      function (snPayload) {
        var merged = {
          username: creds.username,
          password: creds.password,
          new_sn: snPayload.new_sn,
        };
        return Promise.resolve(opts.execute(merged)).then(function (result) {
          handleResult(result);
        });
      },
      opts.onCommitStart || null
    )
      .catch(function (err) {
        if (err && err.message === "cancelled") return;
        throw err;
      })
      .finally(function () {
        if (opts.onFinally) opts.onFinally();
      });
  }

  /**
   * Confirmación de acción con sesión ya validada (sin pedir contraseña de nuevo).
   */
  function runConsultaAltiplanoConfirm(opts) {
    opts = opts || {};
    var creds = opts.creds || readCache();
    if (!creds || !creds.username || !creds.password) {
      return Promise.reject(new Error("Sesión Altiplano no disponible"));
    }

    var dialogOpts = Object.assign(
      { confirmOnly: true, mode: "confirm", useCache: true },
      opts.dialog || {}
    );

    function handleResult(result) {
      var err = authErrorFromResult(result);
      if (err) throw err;
      writeCache(creds.username, creds.password);
      if (opts.onSuccess) opts.onSuccess(result.json, creds);
    }

    return openDialog(
      dialogOpts,
      function () {
        return Promise.resolve(opts.execute(creds)).then(function (result) {
          handleResult(result);
        });
      },
      opts.onCommitStart || null
    )
      .catch(function (err) {
        if (err && err.message === "cancelled") return;
        throw err;
      })
      .finally(function () {
        if (opts.onFinally) opts.onFinally();
      });
  }

  /**
   * Login (si hace falta) + confirmación + acción. Usado por PON / ONT.
   */
  function runConsultaAltiplanoAction(opts) {
    opts = opts || {};
    var loginDialog = Object.assign(
      {
        title: "Ingresar a Altiplano",
        message: "Usuario y contraseña de Altiplano (INP).",
        okLabel: "Ingresar",
      },
      opts.loginDialog || {}
    );

    return ensureConsultaAltiplanoSession({
      operador: opts.operador || "INP",
      forceCredentials: opts.forceCredentials,
      dialog: loginDialog,
    })
      .then(function (creds) {
        return runConsultaAltiplanoConfirm(
          Object.assign({}, opts, { creds: creds })
        );
      })
      .catch(function (err) {
        if (err && err.message === "cancelled") return;
        throw err;
      });
  }

  /** @deprecated Usar runConsultaAltiplanoAction */
  function runConsultaAltiplanoAuth(opts) {
    return runConsultaAltiplanoAction(opts);
  }

  window.runConsultaAltiplanoAuth = runConsultaAltiplanoAuth;
  window.runConsultaAltiplanoAction = runConsultaAltiplanoAction;
  window.runConsultaAltiplanoConfirm = runConsultaAltiplanoConfirm;
  window.runConsultaAltiplanoLogin = runConsultaAltiplanoLogin;
  window.ensureConsultaAltiplanoSession = ensureConsultaAltiplanoSession;
  window.runConsultaSnChange = runConsultaSnChange;
  window.clearConsultaAltiplanoAuthCache = clearCache;
  window.consultaAltiplanoAuthShowError = showError;
})();
