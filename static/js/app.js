/**
 * CCExtractor CI Platform — Modern Vanilla JS
 * Replaces jQuery + Foundation JS
 */

/* ── Navigation: sidebar toggle (mobile) ───────────────────── */
(function () {
  const hamburger = document.getElementById('nav-hamburger');
  const sidebar   = document.getElementById('sidebar');
  const overlay   = document.getElementById('sidebar-overlay');
  if (!hamburger || !sidebar) return;

  function openSidebar() {
    sidebar.classList.add('open');
    if (overlay) overlay.classList.add('open');
    hamburger.setAttribute('aria-expanded', 'true');
    const icon = hamburger.querySelector('i');
    if (icon) { icon.classList.replace('fa-bars', 'fa-xmark'); }
  }
  function closeSidebar() {
    sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('open');
    hamburger.setAttribute('aria-expanded', 'false');
    const icon = hamburger.querySelector('i');
    if (icon) { icon.classList.replace('fa-xmark', 'fa-bars'); }
  }

  hamburger.addEventListener('click', function (e) {
    e.stopPropagation();
    sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
  });
  if (overlay) overlay.addEventListener('click', closeSidebar);

  // Mobile: tap submenu parent to expand/collapse
  sidebar.querySelectorAll('.has-submenu > a').forEach(function (link) {
    link.addEventListener('click', function (e) {
      if (window.innerWidth <= 900) {
        e.preventDefault();
        link.parentElement.classList.toggle('open');
      }
    });
  });
}());


/* ── Theme: dark / light toggle ─────────────────────────────────── */
(function () {
  const btn       = document.getElementById('theme-toggle');
  const iconDark  = document.getElementById('icon-dark');   // moon  — shown in light mode
  const iconLight = document.getElementById('icon-light');  // sun   — shown in dark mode
  const html      = document.documentElement;

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    if (iconDark && iconLight) {
      // Sun shown in light mode, moon shown in dark mode
      iconLight.style.display = (theme === 'dark') ? 'none' : '';
      iconDark.style.display  = (theme === 'dark') ? ''     : 'none';
    }
    if (btn) {
      btn.title = (theme === 'dark') ? 'Switch to light mode' : 'Switch to dark mode';
      btn.setAttribute('aria-label', btn.title);
    }
  }

  // Load saved preference, else respect OS setting
  const saved = localStorage.getItem('theme');
  if (saved) {
    applyTheme(saved);
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    applyTheme('dark');
  }

  if (btn) {
    btn.addEventListener('click', function () {
      const current = html.getAttribute('data-theme');
      const next    = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem('theme', next);
    });
  }

  // Sync with OS preference changes (when no manual override)
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!localStorage.getItem('theme')) applyTheme(e.matches ? 'dark' : 'light');
    });
  }
}());

/* ── CIPlatform: error & loader helpers (vanilla JS) ────────────── */
var CIPlatform = {};

CIPlatform.errorHandler = (function () {
  'use strict';

  function createContent(errors, isFormError) {
    isFormError = isFormError || false;
    if (!Array.isArray(errors) && typeof errors === 'object') {
      // form errors object
      var parts = [];
      for (var f in errors) {
        if (Object.prototype.hasOwnProperty.call(errors, f)) {
          parts = parts.concat(errors[f]);
        }
      }
      errors = parts;
    }
    if (errors.length === 1) return errors[0];
    var content = 'The following errors occurred:<br><ul>';
    errors.forEach(function (e) { content += '<li>' + e + '</li>'; });
    return content + '</ul>';
  }

  function showErrorInElement(el, errors, fadeOut) {
    fadeOut = fadeOut || 0;
    // Accept both DOM elements and jQuery-like objects with [0]
    var domEl = el && el[0] ? el[0] : el;
    if (!domEl) return;
    domEl.style.display = '';
    domEl.innerHTML = createContent(errors);
    if (fadeOut > 0) {
      setTimeout(function () {
        domEl.style.transition = 'opacity 1s';
        domEl.style.opacity = '0';
        setTimeout(function () {
          domEl.style.display = 'none';
          domEl.style.opacity = '';
          domEl.style.transition = '';
        }, 1000);
      }, fadeOut);
    }
  }

  function showErrorInList(listEl, errors) {
    var domEl = listEl && listEl[0] ? listEl[0] : listEl;
    if (!domEl) return;
    domEl.innerHTML = '';
    errors.forEach(function (e) {
      var li = document.createElement('li');
      li.textContent = e;
      domEl.appendChild(li);
    });
    var errMsg = document.getElementById('errorMessage');
    if (errMsg) errMsg.classList.remove('hidden');
  }

  function showFormErrors(loaderEl, formName, errors, prefix) {
    prefix = prefix || '';
    var form = document.forms[formName];
    if (!form) return;
    var formErrors = form.getElementsByClassName('form-errors')[0];
    if (formErrors) formErrors.style.display = '';
    for (var error in errors) {
      if (!Object.prototype.hasOwnProperty.call(errors, error)) continue;
      var field = form[prefix + error];
      if (!field) continue;
      field.classList.add('is-invalid-input');
      field.setAttribute('aria-describedby', field.id + '_error');
      var errEl = document.getElementById(field.id + '_error');
      if (errEl) {
        errEl.textContent = errors[error].join(', ') + '.';
        errEl.classList.add('is-visible');
      }
      var labelEl = form.querySelector('label[for="' + field.id + '"]');
      if (labelEl) labelEl.classList.add('is-invalid-label');
    }
    var loaderDom = loaderEl && loaderEl[0] ? loaderEl[0] : loaderEl;
    if (loaderDom) loaderDom.innerHTML = '';
  }

  function clearFormErrors(formName) {
    var form = document.forms[formName];
    if (!form) return;
    var formErrors = form.getElementsByClassName('form-errors')[0];
    if (formErrors) formErrors.style.display = 'none';
    Array.from(form.elements).forEach(function (field) {
      field.classList.remove('is-invalid-input');
      var helpText = document.getElementById(field.id + '_help_text');
      if (helpText) field.setAttribute('aria-describedby', field.id + '_help_text');
      var errEl = document.getElementById(field.id + '_error');
      if (errEl) { errEl.textContent = ''; errEl.classList.remove('is-visible'); }
      if (field.id) {
        var labelEl = form.querySelector('label[for="' + field.id + '"]');
        if (labelEl) labelEl.classList.remove('is-invalid-label');
      }
    });
  }

  function showErrorInPopup(errors, needsPageReload) {
    var overlay = document.createElement('div');
    overlay.style.cssText = [
      'position:fixed;inset:0;background:rgba(0,0,0,0.65);z-index:9999;',
      'display:flex;align-items:center;justify-content:center;',
      'animation:fadeIn 0.2s ease;'
    ].join('');

    var modal = document.createElement('div');
    modal.style.cssText = [
      'background:var(--bg-surface);border-radius:var(--radius-lg);',
      'padding:2rem;max-width:560px;width:90%;position:relative;',
      'box-shadow:var(--shadow-lg);border:1px solid var(--border);'
    ].join('');
    modal.innerHTML = createContent(errors, true);

    if (needsPageReload) {
      modal.innerHTML += '<p style="margin-top:1rem"><strong>Please reload the page to get the current state.</strong></p>';
    }

    var closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.className = 'button secondary small';
    closeBtn.style.cssText = 'position:absolute;top:1rem;right:1rem;';
    closeBtn.addEventListener('click', function () { document.body.removeChild(overlay); });
    modal.appendChild(closeBtn);

    overlay.appendChild(modal);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) document.body.removeChild(overlay);
    });
    document.body.appendChild(overlay);
  }

  return {
    showErrorInElement : showErrorInElement,
    showErrorInList    : showErrorInList,
    showFormErrors     : showFormErrors,
    clearFormErrors    : clearFormErrors,
    showErrorInPopup   : showErrorInPopup,
    registerListeners  : function () {} // kept for backward compatibility
  };
}());

CIPlatform.loadHandler = (function () {
  'use strict';
  var defaultIcon = 'fa-gear';
  var defaultText = 'Please wait while we process the request\u2026';

  function showLoaderInElement(el, loaderIcon, loaderText) {
    loaderIcon = loaderIcon || defaultIcon;
    loaderText = loaderText || defaultText;
    var domEl = el && el[0] ? el[0] : el;
    if (domEl) {
      domEl.innerHTML = '<i class="fa-solid fa-spin ' + loaderIcon + '" aria-hidden="true"></i> ' + loaderText;
    }
  }

  return { showLoaderInElement: showLoaderInElement };
}());