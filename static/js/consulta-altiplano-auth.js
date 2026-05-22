/**
 * Autenticación Altiplano en consulta índice: modal, errores inline y caché de sesión.
 */
(function () {
  "use strict";

  var CACHE_KEY = "atc_noc_consulta_altiplano_auth";
  var CACHE_TTL_MS = 30 * 60 * 1000;

  var wired = false;
  var pendingResolve = null;
  var pendingReject = null;
  var pendingSubmit = null;
  var pendingOnCommitStart = null;
  var lastDialogOpts = null;
  var dialogLoading = false;

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
          exp: Date.now() + CACHE_TTL_MS,
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

  function setSessionBar(cache, forceHidden) {
    var bar = el("consulta-altiplano-auth-session");
    var userTxt = el("consulta-altiplano-auth-session-user");
    var ttlTxt = el("consulta-altiplano-auth-session-ttl");
    var credsWrap = el("consulta-altiplano-auth-creds-wrap");
    if (!bar) return;
    if (forceHidden || !cache) {
      bar.hidden = true;
      if (credsWrap) credsWrap.hidden = false;
      return;
    }
    bar.hidden = false;
    if (userTxt) userTxt.textContent = cache.username;
    if (ttlTxt) {
      ttlTxt.textContent =
        "Sesión activa · " + cacheMinutesLeft(cache.expiresAt) + " min restantes";
    }
    if (credsWrap) credsWrap.hidden = true;
  }

  function showCredentialsForm(prefill) {
    clearCache();
    setSessionBar(null, true);
    var userEl = el("consulta-altiplano-auth-user");
    var pwdEl = el("consulta-altiplano-auth-password");
    if (userEl) userEl.value = (prefill && prefill.username) || "";
    if (pwdEl) pwdEl.value = (prefill && prefill.password) || "";
    if (userEl) userEl.focus();
  }

  function closeDialog(result) {
    var dlg = el("consulta-altiplano-auth-dialog");
    setDialogLoading(false);
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

  /** Cierra el modal sin cancelar la operación en curso. */
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
    if (wired) return;
    var dlg = el("consulta-altiplano-auth-dialog");
    if (!dlg) return;
    wired = true;

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
    var snEl = el("consulta-altiplano-auth-sn");
    var snWrap = el("consulta-altiplano-auth-sn-wrap");
    var credsWrap = el("consulta-altiplano-auth-creds-wrap");
    var cache = readCache();
    var credsHidden = credsWrap && credsWrap.hidden && cache;

    var username = "";
    var password = "";
    if (credsHidden) {
      username = cache.username;
      password = cache.password;
    } else {
      username = userEl ? String(userEl.value || "").trim() : "";
      password = pwdEl ? String(pwdEl.value || "") : "";
    }

    if (!username || !password) {
      showError("Completá usuario y contraseña de Altiplano.");
      if (!credsHidden) {
        if (!username && userEl) userEl.focus();
        else if (pwdEl) pwdEl.focus();
      }
      return null;
    }

    var payload = { username: username, password: password };
    if (snWrap && !snWrap.hidden && snEl) {
      var sn = String(snEl.value || "").trim().toUpperCase();
      if (!sn) {
        showError("Ingresá el nuevo SN.");
        snEl.focus();
        return null;
      }
      if (sn.length < 6 || sn.length > 32) {
        showError("SN inválido (entre 6 y 32 caracteres).");
        snEl.focus();
        return null;
      }
      payload.new_sn = sn;
    }
    return payload;
  }

  function submitFromForm() {
    if (dialogLoading) return;
    var payload = collectCredentialsFromForm();
    if (!payload) return;
    clearError();
    if (pendingSubmit) {
      var submitFn = pendingSubmit;
      var commitStart = pendingOnCommitStart;
      if (commitStart) commitStart(payload);
      dismissDialog();
      submitFn(payload)
        .then(function () {
          finalizeSubmitSuccess(payload);
        })
        .catch(function (err) {
          var rej = pendingReject;
          pendingResolve = null;
          pendingReject = null;
          pendingSubmit = null;
          pendingOnCommitStart = null;
          if (rej) rej(err);
          else throw err;
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
    var snEl = el("consulta-altiplano-auth-sn");
    var snWrap = el("consulta-altiplano-auth-sn-wrap");
    var btnOk = el("consulta-altiplano-auth-ok");
    var cache = opts.useCache !== false ? readCache() : null;

    if (titleEl) titleEl.textContent = opts.title || "Confirmar en Altiplano";
    if (msgEl) {
      var msg = opts.message || "";
      msgEl.textContent = msg;
      msgEl.hidden = !msg;
    }
    if (snWrap) snWrap.hidden = !opts.showSnField;
    if (snEl && opts.showSnField) {
      snEl.value = opts.snValue != null ? String(opts.snValue) : "";
      if (opts.snPlaceholder) snEl.placeholder = opts.snPlaceholder;
    }
    if (btnOk) {
      btnOk.textContent =
        opts.okLabel || (opts.showSnField ? "Cambiar SN" : "Confirmar");
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

    if (cache && !opts.forceCredentials) {
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
      var snWrap = el("consulta-altiplano-auth-sn-wrap");
      var snEl = el("consulta-altiplano-auth-sn");
      var credsWrap = el("consulta-altiplano-auth-creds-wrap");
      if (snWrap && !snWrap.hidden && snEl) snEl.focus();
      else if (credsWrap && !credsWrap.hidden) {
        var userEl = el("consulta-altiplano-auth-user");
        if (userEl) userEl.focus();
      }
    });
  }

  /**
   * Ejecuta una acción con credenciales Altiplano (modal o caché de sesión).
   *
   * @param {object} opts
   * @param {object} opts.dialog — título, mensaje, showSnField, danger, etc.
   * @param {function} opts.execute — (creds) => Promise<{ok,status,json}>
   * @param {function} [opts.onSuccess] — (json, creds) => void
   * @param {function} [opts.onFinally] — () => void
   * @param {function} [opts.onCommitStart] — (creds) => void, al confirmar (antes del fetch)
   */
  function runConsultaAltiplanoAuth(opts) {
    opts = opts || {};
    var dialogOpts = opts.dialog || {};
    var needsSn = Boolean(dialogOpts.showSnField);
    var cache = readCache();

    function handleResult(result, creds) {
      if (result.status === 401) {
        clearCache();
        var msg =
          (result.json && result.json.message) ||
          "Usuario o contraseña incorrectos. Verificá las credenciales de Altiplano.";
        var err = Object.assign(new Error(msg), { authError: true });
        throw err;
      }
      if (!result.ok || !result.json || !result.json.ok) {
        throw new Error(
          (result.json && result.json.message) ||
            "No se pudo completar la operación en Altiplano."
        );
      }
      writeCache(creds.username, creds.password);
      if (opts.onSuccess) opts.onSuccess(result.json, creds);
    }

    function runExecute(creds) {
      return Promise.resolve(opts.execute(creds)).then(function (result) {
        return handleResult(result, creds);
      });
    }

    function openWithSubmit(extraDialog) {
      var merged = Object.assign({}, dialogOpts, extraDialog || {});
      return openDialog(
        merged,
        function (creds) {
          return runExecute(creds);
        },
        opts.onCommitStart || null
      ).catch(function (err) {
        if (err && err.message === "cancelled") return;
        throw err;
      });
    }

    if (cache && !needsSn && !dialogOpts.forceCredentials) {
      return runExecute(cache)
        .catch(function (err) {
          if (err && err.authError) {
            return openWithSubmit({
              forceCredentials: true,
              initialError: err.message,
              prefillUser: cache.username,
            });
          }
          throw err;
        })
        .finally(function () {
          if (opts.onFinally) opts.onFinally();
        });
    }

    return openWithSubmit(
      cache && !dialogOpts.forceCredentials
        ? { useCache: true }
        : { useCache: false }
    ).finally(function () {
      if (opts.onFinally) opts.onFinally();
    });
  }

  window.runConsultaAltiplanoAuth = runConsultaAltiplanoAuth;
  window.clearConsultaAltiplanoAuthCache = clearCache;
  window.consultaAltiplanoAuthShowError = showError;
})();
