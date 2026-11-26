(function () {
  // Language switcher (default: English)
  function applyLang(lang) {
    document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en';
    document.querySelectorAll('[data-en][data-pt]').forEach(function (el) {
      el.textContent = el.getAttribute('data-' + lang);
    });
    // Tooltips and labels on icon buttons: they are attributes, not text
    // nodes, so they need their own pass.
    document.querySelectorAll('[data-en-title][data-pt-title]').forEach(function (el) {
      var label = el.getAttribute('data-' + lang + '-title');
      el.setAttribute('title', label);
      el.setAttribute('aria-label', label);
    });
    // Rendered Markdown: one block per language in the same container. An
    // item written in a single language keeps showing that one.
    document.querySelectorAll('[data-lang-bodies]').forEach(function (group) {
      var chosen = group.querySelector('[data-lang-body="' + lang + '"]')
        || group.querySelector('[data-lang-body][data-lang-default]');
      group.querySelectorAll('[data-lang-body]').forEach(function (block) {
        block.classList.toggle('hidden', block !== chosen);
      });
    });
    document.querySelectorAll('[data-lang]').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-lang') === lang);
    });
    try { localStorage.setItem('rikalves_lang', lang); } catch (e) {}
  }

  var initialLang = 'en';
  try {
    var saved = localStorage.getItem('rikalves_lang');
    if (saved === 'pt' || saved === 'en') initialLang = saved;
  } catch (e) {}
  applyLang(initialLang);

  // Filters + AOI filtering
  var activeFilter = 'all';
  var activeAoi = 'all';

  function updateFilteredList() {
    document.querySelectorAll('[data-list-item]').forEach(function (item) {
      var cat = item.getAttribute('data-category') || 'all';
      var aoi = item.getAttribute('data-aoi') || 'all';
      var matchCat = activeFilter === 'all' || cat === activeFilter;
      var matchAoi = activeAoi === 'all' || aoi === activeAoi;
      item.classList.toggle('hidden', !(matchCat && matchAoi));
    });
  }

  document.addEventListener('click', function (e) {
    var langBtn = e.target.closest('[data-lang]');
    if (langBtn) {
      applyLang(langBtn.getAttribute('data-lang'));
      return;
    }

    var menuBtn = e.target.closest('#btn-mobile-menu');
    if (menuBtn) {
      var drawer = document.getElementById('mobile-drawer');
      if (drawer) drawer.classList.toggle('hidden');
      return;
    }

    var filterBtn = e.target.closest('[data-filter]');
    if (filterBtn) {
      activeFilter = filterBtn.getAttribute('data-filter');
      document.querySelectorAll('[data-filter]').forEach(function (b) {
        b.classList.toggle('is-active', b === filterBtn);
      });
      updateFilteredList();
      return;
    }

    var aoiToggle = e.target.closest('#btn-aoi');
    if (aoiToggle) {
      var aoiDrawer = document.getElementById('aoi-drawer');
      if (aoiDrawer) {
        var open = aoiDrawer.classList.toggle('hidden');
        aoiToggle.classList.toggle('is-active', !open);
      }
      return;
    }

    var aoiPin = e.target.closest('[data-aoi-select]');
    if (aoiPin) {
      activeAoi = aoiPin.getAttribute('data-aoi-select');
      document.querySelectorAll('[data-aoi-select]').forEach(function (p) {
        p.classList.toggle('is-active', p.getAttribute('data-aoi-select') === activeAoi && activeAoi !== 'all');
      });
      var clearBtn = document.getElementById('btn-aoi-clear');
      if (clearBtn) clearBtn.classList.toggle('hidden', activeAoi === 'all');
      updateFilteredList();
      return;
    }

    var citeBtn = e.target.closest('[data-cite-target]');
    if (citeBtn) {
      var targetId = citeBtn.getAttribute('data-cite-target');
      var block = document.getElementById(targetId);
      if (block) {
        var nowHidden = block.classList.toggle('hidden');
        citeBtn.classList.toggle('is-active', !nowHidden);
      }
      return;
    }

    var copyBtn = e.target.closest('[data-copy-target]');
    if (copyBtn) {
      var src = document.getElementById(copyBtn.getAttribute('data-copy-target'));
      if (!src) return;
      var text = src.textContent.trim();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(function () {});
      }
      copyBtn.classList.add('is-active');
      setTimeout(function () { copyBtn.classList.remove('is-active'); }, 1400);
    }
  });
})();
