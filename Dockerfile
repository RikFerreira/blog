# syntax=docker/dockerfile:1
# check=skip=SecretsUsedInArgOrEnv
#
# The skip is for MAP_TILES_KEY below. BuildKit flags any ARG whose name
# looks like a credential, and it is right that this one is readable in the
# image: a static site hands the tile key to every visitor, so it is not a
# secret to begin with and is restricted by domain at the provider instead.
# Without the skip the warning fires on every build and trains everyone to
# ignore warnings.

# ---------------------------------------------------------------------------
# Build stage: render the site with the generator in frontend/build.py.
#
# Pinned to BUILDPLATFORM on purpose. The output is static HTML/CSS/JS and is
# identical whatever architecture produced it, so this keeps Python off QEMU
# when the target is linux/arm64.
# ---------------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM python:3.13-slim-bookworm AS builder

# Baked into every absolute URL the generator emits. Override with the public
# origin, e.g. --build-arg SITE_BASE_URL=https://rikalves.com/
ARG SITE_BASE_URL=/

# Vector tile key for the AOI map. A static site hands it to every visitor, so
# restrict it by domain at the provider. Without it the map falls back to a
# plain background and the build warns.
ARG MAP_TILES_KEY=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src

# Dependencies first, so editing content does not invalidate this layer.
COPY frontend/requirements.txt frontend/requirements.txt
# --root-user-action=ignore: the venv pip suggests buys nothing in a
# container that runs one program.
RUN pip install --no-cache-dir --root-user-action=ignore -r frontend/requirements.txt

# Third-party browser code, pinned and checksummed in frontend/vendor.toml.
# Fetched before the content is copied, so the ~1.6MB download is cached
# until that file changes. It lands in frontend/site/vendor, which the COPY
# below merges into rather than replaces.
COPY frontend/build.py frontend/vendor.toml frontend/
RUN python frontend/build.py --vendor

COPY frontend frontend

RUN SITE_BASE_URL="${SITE_BASE_URL}" MAP_TILES_KEY="${MAP_TILES_KEY}" \
    python frontend/build.py

# ---------------------------------------------------------------------------
# Runtime stage: nginx serving the rendered site.
# No --platform here, so it resolves to the target (linux/arm64), and no RUN,
# so nothing has to execute under emulation.
# ---------------------------------------------------------------------------
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /src/frontend/site /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
