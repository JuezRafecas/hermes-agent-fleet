# hermes-agent-fleet — thin derived image over the official Hermes release.
# NOT a fork: zero edits to Hermes source. We only add OS tooling, a headless
# X server as an s6 service, and the cua-driver binary for computer_use.
FROM nousresearch/hermes-agent:v2026.8.27@sha256:e0df6adebddf29b91112aefc999d4aaf6846c9eb544faca5672a16a13590ff79

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ---------------------------------------------------------------------------
# OS tooling agents can use from the terminal toolset.
#   xvfb/x11-utils/xdotool -> headless desktop for computer_use
#   jq/ripgrep             -> data wrangling (ripgrep is already in base; kept
#                             explicit so the contract does not depend on it)
#   postgresql-client      -> psql against trainer/recommender stores
#   mongosh                -> MongoDB administration and read-only probes
#   gh                     -> GitHub CLI
# ---------------------------------------------------------------------------
RUN set -eux; \
    apt-get -o Acquire::Retries=3 update; \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
        xvfb x11-utils xdotool jq ripgrep postgresql-client \
        gnupg ca-certificates curl; \
    install -m 0755 -d /usr/share/keyrings; \
    # --- MongoDB apt repo (mongosh only). The repo has no trixie suite yet, so
    # we point at the bookworm suite; mongosh is a self-contained Node bundle
    # and installs cleanly. If apt ever fails, fall back to the upstream tgz.
    curl -fsSL https://pgp.mongodb.com/server-8.0.asc \
        | gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg; \
    echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" \
        > /etc/apt/sources.list.d/mongodb-org-8.0.list; \
    # --- GitHub CLI apt repo
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list; \
    apt-get -o Acquire::Retries=3 update; \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends gh; \
    { apt-get -o Acquire::Retries=3 install -y --no-install-recommends mongodb-mongosh; } || { \
        arch="$(dpkg --print-architecture)"; \
        case "$arch" in amd64) m=x64 ;; arm64) m=arm64 ;; *) m="" ;; esac; \
        [ -n "$m" ] && curl -fsSL --retry 3 -o /tmp/mongosh.tgz \
            "https://downloads.mongodb.com/compass/mongosh-2.3.8-linux-${m}.tgz" && \
        tar -xzf /tmp/mongosh.tgz -C /tmp && \
        install -m 0755 /tmp/mongosh-*/bin/mongosh /usr/local/bin/mongosh && \
        rm -rf /tmp/mongosh*; \
    }; \
    rm -rf /var/lib/apt/lists/*; \
    mongosh --version; gh --version >/dev/null; command -v Xvfb xdotool psql jq rg

# ---------------------------------------------------------------------------
# cua-driver for the computer_use toolset.
# `hermes computer-use install` drops the binary under $HERMES_HOME
# (.cua-driver/ + .local/bin/cua-driver). At runtime HERMES_HOME=/opt/data is
# shadowed by the bind mount, so we install with HERMES_HOME redirected to
# the image layer. The shim forces HERMES_HOME=/opt/data (a VOLUME, so its
# contents vanish after the RUN step): we copy the binary out to
# /usr/local/libexec inside the same step and point Hermes at its wrapper with
# HERMES_CUA_DRIVER_CMD, which the resolver treats as authoritative
# (tools/computer_use/cua_backend.py). Linux support is alpha upstream.
# Best-effort: a network blip must not fail the whole build.
# ---------------------------------------------------------------------------
RUN set -eux; \
    if /opt/hermes/bin/hermes computer-use install >/tmp/cua.log 2>&1; then \
        bin="$(find / -xdev -type f -name cua-driver -path '*releases*' -not -path '/proc/*' 2>/dev/null | head -1)"; \
        test -n "$bin"; \
        install -m 0755 "$bin" /usr/local/libexec/cua-driver; \
        /usr/local/libexec/cua-driver --help >/dev/null 2>&1 || true; \
        echo "cua-driver copied from $bin"; \
    else \
        echo "WARN: cua-driver install failed at build time"; tail -20 /tmp/cua.log || true; \
    fi
# agent-browser: la CLI que usa el toolset `browser` de Hermes (headless Chromium).
RUN set -eux; npm install -g --no-audit --no-fund agent-browser pnpm @aws-sdk/client-s3 @neondatabase/mcp-server-neon mongodb-mcp-server@2.1.0; agent-browser --version || true; pnpm --version
ENV NODE_PATH=/usr/local/lib/node_modules
# git usa el GH_TOKEN global vía gh, sin importar el HOME del perfil
RUN git config --system credential.helper "!gh auth git-credential" && \
    install -d -m 0755 /usr/local/share/hermes
# wrappers de MCP por perfil (leen la key del .env del perfil): neon-mcp, mongo-mcp
COPY --chmod=0755 config/bin/ /usr/local/bin/
COPY --chmod=0755 scripts/profile-displays.py /usr/local/libexec/profile-displays.py
COPY --chmod=0644 config/profile-display-env.sh /usr/local/share/hermes/profile-display-env.sh
ENV HERMES_CUA_DRIVER_CMD=/usr/local/bin/cua-driver
ENV BASH_ENV=/usr/local/share/hermes/profile-display-env.sh
# shared-file-upload: publish human-facing artifacts to an S3-compatible drop.
COPY --chmod=0755 config/skills-shared/shared-file-drop/shared-file-upload.mjs /usr/local/lib/node_modules/shared-file-upload/index.mjs
RUN ln -sf /usr/local/lib/node_modules/shared-file-upload/index.mjs /usr/local/bin/shared-file-upload

# ---------------------------------------------------------------------------
# Headless display pool as one s6-rc longrun, mirroring the image's own
# `dashboard` service layout and registered in the `user` bundle. It owns ten
# Xvfb children (:100..:109); the profile-aware cua-driver wrapper selects one.
# ---------------------------------------------------------------------------
COPY --chmod=0755 s6/xvfb/run /etc/s6-overlay/s6-rc.d/xvfb/run
COPY s6/xvfb/type /etc/s6-overlay/s6-rc.d/xvfb/type
COPY s6/xvfb/dependencies.d/base /etc/s6-overlay/s6-rc.d/xvfb/dependencies.d/base
RUN touch /etc/s6-overlay/s6-rc.d/user/contents.d/xvfb
