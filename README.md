# blog

Hugo site built on the [Hugo Blox Academic CV](https://hugoblox.com/templates/academic-cv)
template, shipped as an nginx container image on `ghcr.io/rikferreira/blog`.

The site is rendered during the image build, not in this repo. Nothing in
`public/` is committed.

## Layout

| Path | Purpose |
| --- | --- |
| `config/_default/` | Hugo configuration — site params, menus, languages, modules |
| `content/` | Pages, posts, publications, talks, projects |
| `content/_index.md` | Homepage: which blocks appear and in what order |
| `data/authors/me.yaml` | Your profile — name, bio, education, interests, links |
| `assets/`, `static/` | Images, media, CSS overrides |
| `Dockerfile` | Two-stage build: render with Hugo, serve with nginx |
| `nginx.conf` | Server block used inside the image |
| `.github/workflows/publish.yml` | Builds and pushes the image to GHCR |

Start with `data/authors/me.yaml` (name, bio, social links), then
`config/_default/params.yaml` (site branding, colors, analytics) and
`config/_default/menus.yaml` (navigation). The avatar is
`assets/media/authors/me.png`.

## Image build

The build stage is pinned to `$BUILDPLATFORM` and the nginx stage to the target
platform. Hugo output is static, so an amd64 runner can produce a linux/arm64
image without QEMU. Adding a `RUN` to the final stage would break that.

```bash
docker buildx build --platform linux/arm64 \
  --build-arg HUGO_BASEURL=https://example.com/ \
  -t ghcr.io/rikferreira/blog:latest .
```

`HUGO_BASEURL` defaults to `/`, which emits root-relative URLs and works behind
any hostname. Set it to the real origin if you need absolute URLs in the RSS
feed, sitemap and Open Graph tags.

## Publishing

`.github/workflows/publish.yml` runs on pushes to `main` and on `v*` tags, and
pushes `linux/arm64` images tagged `latest`, `sha-<short>`, and the tag name.
Pull requests build without pushing.

To bake a real origin into the published image, set the repository variable
`SITE_BASE_URL` (Settings → Secrets and variables → Actions → Variables).

GHCR packages are private on first push. Either make the package public, or give
the host running the image a read token:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u rikferreira --password-stdin
```

## Consuming it

In the other repo's `docker-compose.yaml`:

```yaml
services:
  blog:
    image: ghcr.io/rikferreira/blog:latest
    restart: unless-stopped
    ports:
      - "8080:80"
```

## Local development

Needs Hugo extended ≥ 0.162, Go, and Node ≥ 22.15 (Hugo's Tailwind integration
calls `module.registerHooks()`).

```bash
corepack enable
pnpm install
pnpm dev          # http://localhost:1313
```
