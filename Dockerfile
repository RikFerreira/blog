# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage: render the Hugo site.
#
# Pinned to BUILDPLATFORM on purpose. The output is static HTML/CSS/JS and is
# identical whatever architecture produced it, so this keeps the toolchain
# (Go, Node, Hugo, Pagefind) off QEMU when the target is linux/arm64.
# ---------------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM golang:1.25-bookworm AS go

# Node 24: Hugo's Tailwind integration needs module.registerHooks(), which
# landed in Node 22.15 / 24.
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS builder

ARG HUGO_VERSION=0.162.1
ARG BUILDARCH
# Baked into every absolute URL Hugo emits. Override with the public origin,
# e.g. --build-arg HUGO_BASEURL=https://rikalves.com/
ARG HUGO_BASEURL=/

ENV PATH=/usr/local/go/bin:$PATH \
    GOPATH=/go \
    HUGO_ENV=production \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
COPY --from=go /usr/local/go /usr/local/go

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && curl -fsSL -o /tmp/hugo.deb \
      "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-${BUILDARCH}.deb" \
 && apt-get install -y --no-install-recommends /tmp/hugo.deb \
 && rm -rf /tmp/hugo.deb /var/lib/apt/lists/*

WORKDIR /src

# Dependencies first, so editing content does not invalidate these layers.
COPY package.json pnpm-lock.yaml .npmrc ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN hugo --gc --minify --baseURL "${HUGO_BASEURL}" \
 && pnpm exec pagefind --site public

# ---------------------------------------------------------------------------
# Runtime stage: nginx serving the rendered site.
# No --platform here, so it resolves to the target (linux/arm64).
# ---------------------------------------------------------------------------
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /src/public /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
