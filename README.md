# rikalves.com

Personal site, rendered by a static site generator written for it:
`frontend/build.py` reads `frontend/content/` (Markdown, TOML, assets) and
writes `frontend/site/`, which nginx serves from the container image
`ghcr.io/rikferreira/blog`.

The previous version was built on Hugo. It was removed in favour of this
generator; the old content is kept out of git under `archive/hugo-site/` until
it has been ported.

## Layout

| Path | Purpose |
| --- | --- |
| `frontend/build.py` | The generator |
| `frontend/content/` | Everything written by hand — Markdown, TOML, assets |
| `frontend/themes/blog-plain/` | Templates, interface strings, CSS and JS |
| `frontend/site/` | Rendered output. Built inside the image, never committed |
| `frontend/tests/` | pytest suite for the generator |
| `backend/` | Reserved, empty |
| `Dockerfile`, `nginx.conf` | Build the site, then serve it |

Build instructions land with the Dockerfile rewrite.
