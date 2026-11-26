# rikalves.com

Personal site, rendered by a static site generator written for it.
`frontend/build.py` reads `frontend/content/` — Markdown, TOML and assets —
and writes `frontend/site/`, which nginx serves from the container image
`ghcr.io/rikferreira/blog` (linux/arm64).

The site is rendered during the image build. Nothing in `frontend/site/` is
committed.

## Layout

| Path | Purpose |
| --- | --- |
| `frontend/build.py` | The generator — loading, validation, rendering, assets |
| `frontend/content/` | Everything written by hand |
| `frontend/themes/blog-plain/` | Templates, interface strings, icons, CSS and JS |
| `frontend/vendor.toml` | Pinned third-party browser code and its checksums |
| `frontend/tests/` | pytest suite |
| `backend/` | Reserved, empty |
| `Dockerfile`, `nginx.conf` | Build the site, then serve it |

## Writing content

Three levels:

```
content/
    index.toml                       the homepage and everything global
    posts/
        posts.toml                   the section: sorting and filters
        a-post/
            content.en.md            the item, one file per language
            content.pt.md
            assets/cover.png
```

`index.toml` holds `[site]`, `[profile]`, `[home]`, `[[nav]]`, `[[links]]` and
`[map]`. A section's TOML holds `[section]` with `kind` (`post`, `publication`,
`project` or `cv`), `sort` (`date` or `title`), `order`, `filter` (`tags` or
`language`) and `map`.

### Front matter

```yaml
---
title: Title of the content
subtitle: Description of the content
date: 2026-11-04
cover: assets/image.png
tags: [Remote Sensing, Sentinel-2]
language: en
ai_written: false
external_link: https://external-link.com/
source_repo: https://git-repo.com/
aoi_wkt: POLYGON ((...))
citation: cite.bib
---
```

Only these keys are accepted; anything else fails the build, as does a
`language` that disagrees with the file name, a malformed date, or a `cover`
or `citation` pointing at a file that is not there.

`title` is required in every language file. The file in the default language
is the primary one and supplies the rest — `date`, `tags`, `cover` and the
others describe the item, not one translation of it.

### Two languages, one URL

An item renders to a single page carrying every language it was written in.
The EN/PT selector swaps the interface and the body of the text together. An
item written in one language only shows that one, with a badge saying so.

Interface strings live in `frontend/themes/blog-plain/i18n/*.toml`, never in
the templates. A key missing from either file fails the test suite.

### Areas of interest

A publication's `aoi_wkt` is parsed at build time into
`site/publications/aois.geojson` and drawn by MapLibre in the AOI drawer.
Clicking a polygon filters the list. Style and the vector tile URL come from
`[map]` in `index.toml`:

```toml
[map]
style         = "https://api.maptiler.com/maps/dataviz-light/style.json?key=${MAP_TILES_KEY}"
max_vertices  = 500
line_color    = "#111111"
line_width    = 1.9        # px, about 0.5mm at 96dpi
fill_color    = "#111111"
fill_opacity  = 0.06
active_color  = "#c83223"
```

Geometries over `max_vertices` are thinned. Without `MAP_TILES_KEY` the build
warns and the map falls back to a plain background, so a local run needs no
account anywhere.

## Local development

Needs Python 3.13.

```bash
cd frontend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt

.venv/Scripts/python -m pytest
.venv/Scripts/python build.py --vendor        # once, downloads MapLibre
.venv/Scripts/python build.py                 # renders site/
.venv/Scripts/python -m http.server -d site 8000
```

Serve the output rather than opening the files directly: pages reference
assets by absolute path, and the AOI map fetches its GeoJSON.

## Image build

The build stage is pinned to `$BUILDPLATFORM` and the nginx stage to the
target platform. The output is static, so an amd64 runner produces a
linux/arm64 image without QEMU. Adding a `RUN` to the final stage would break
that.

```bash
docker buildx build --platform linux/arm64 \
  --build-arg SITE_BASE_URL=https://rikalves.com/ \
  --build-arg MAP_TILES_KEY="$MAP_TILES_KEY" \
  -t ghcr.io/rikferreira/blog:latest .
```

`SITE_BASE_URL` defaults to `/`, which emits root-relative URLs and works
behind any hostname.

The tile key is public in a static site by nature — it is handed to every
visitor. Restrict it by domain at the provider; keeping it out of the
repository is housekeeping, not secrecy.

## Publishing

`.github/workflows/publish.yml` runs the test suite, then builds and pushes
`linux/arm64` images tagged `latest`, `sha-<short>` and any `v*` tag. Pull
requests build without pushing. Set the repository variables `SITE_BASE_URL`
and `MAP_TILES_KEY` under Settings, Secrets and variables, Actions, Variables.

A push here is not a deploy. The host's compose file in `RikFerreira/webgis`
pins `ghcr.io/rikferreira/blog:sha-<short>`, so rikalves.com keeps serving the
old commit until that pin is moved.

## The previous site

This replaced a Hugo site built on the Hugo Blox Academic CV template. Its
content is kept out of git under `archive/hugo-site/`, alongside the frontend
handoff the theme was built from, until it has been ported.
