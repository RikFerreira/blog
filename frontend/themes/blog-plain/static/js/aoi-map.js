/* The AOI map.
 *
 * Draws the areas of interest the generator extracted from each item's
 * aoi_wkt, and bridges the map to the list filter site.js already runs:
 * clicking a polygon is the same event as clicking an AOI control, so the
 * list filters without either script knowing about the other.
 */
(function () {
  var container = document.getElementById('aoi-map');
  var configEl = document.getElementById('aoi-config');
  if (!container || !configEl || typeof maplibregl === 'undefined') return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    return;
  }

  var SOURCE = 'aois';
  var map = null;
  var collection = null;
  var selected = null;

  // The drawer starts hidden, so the canvas has no size until it opens.
  // Build the map on first open and let MapLibre measure itself then.
  function ensureMap() {
    if (map) {
      map.resize();
      if (collection) fitAll();
      return;
    }

    map = new maplibregl.Map({
      container: container,
      style: config.style,
      center: [0, 0],
      zoom: 1,
      attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.on('load', function () {
      fetch(config.source)
        .then(function (response) { return response.json(); })
        .then(addLayers)
        .catch(function () {});
    });
  }

  function addLayers(data) {
    collection = data;
    map.addSource(SOURCE, { type: 'geojson', data: data, promoteId: 'slug' });

    map.addLayer({
      id: 'aoi-fill',
      type: 'fill',
      source: SOURCE,
      paint: {
        'fill-color': config.fill_color,
        'fill-opacity': [
          'case', ['boolean', ['feature-state', 'selected'], false],
          Math.min(1, config.fill_opacity * 2.5),
          config.fill_opacity
        ]
      }
    });

    map.addLayer({
      id: 'aoi-line',
      type: 'line',
      source: SOURCE,
      paint: {
        'line-color': [
          'case', ['boolean', ['feature-state', 'selected'], false],
          config.active_color,
          config.line_color
        ],
        'line-width': config.line_width
      }
    });

    map.on('click', 'aoi-fill', function (event) {
      var feature = event.features && event.features[0];
      if (feature) select(feature.properties.slug);
    });
    map.on('mouseenter', 'aoi-fill', function () {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'aoi-fill', function () {
      map.getCanvas().style.cursor = '';
    });

    fitAll();
  }

  function fitAll() {
    if (!collection || !collection.bbox) return;
    map.fitBounds(
      [[collection.bbox[0], collection.bbox[1]], [collection.bbox[2], collection.bbox[3]]],
      { padding: config.padding, maxZoom: config.max_zoom, duration: 0 }
    );
  }

  function paint(slug, isSelected) {
    if (!slug || !map.getSource(SOURCE)) return;
    map.setFeatureState({ source: SOURCE, id: slug }, { selected: isSelected });
  }

  // Hand the choice to site.js, which owns the list filtering, by clicking a
  // hidden control carrying the same data-aoi-select attribute it listens for.
  function select(slug) {
    var next = slug === selected ? 'all' : slug;
    var proxy = document.createElement('button');
    proxy.type = 'button';
    proxy.setAttribute('data-aoi-select', next);
    proxy.className = 'hidden';
    document.body.appendChild(proxy);
    proxy.click();
    proxy.remove();
  }

  // site.js announces the active area; repaint to match, however it changed.
  document.addEventListener('click', function (event) {
    var control = event.target.closest('[data-aoi-select]');
    if (control) {
      var next = control.getAttribute('data-aoi-select');
      paint(selected, false);
      selected = next === 'all' ? null : next;
      paint(selected, true);
      return;
    }
    if (event.target.closest('#btn-aoi')) {
      // Let the drawer finish toggling before measuring the canvas.
      window.setTimeout(function () {
        var drawer = document.getElementById('aoi-drawer');
        if (drawer && !drawer.classList.contains('hidden')) ensureMap();
      }, 0);
    }
  });
})();
