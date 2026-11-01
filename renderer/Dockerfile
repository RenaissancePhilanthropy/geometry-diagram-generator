# Build from project root: docker build -f renderer/Dockerfile .
# Pinned by tag and digest (TeX Live 2026, dvisvgm 3.6). `latest` moves monthly
# and has broken renders before. To upgrade, change the tag and digest together,
# rebuild, and check a render and the container tests. TeX packages below come
# from the repository matching this TeX Live year; once the next TeX Live
# releases, bump this tag first (an older base cannot install from the newer
# repository). Packages are not frozen within the year; freezing them needs a
# historic tlnet-final repository (`tlmgr option repository <url>`), which was
# not reachable from the build environment when this was written.
FROM --platform=linux/amd64 reitzig/texlive-base-luatex:2026.9@sha256:8d3e97d7a963e2e9903606da2f8417fdc219348b03dc1cd0a5eee937f3145ebe

# Install TeX packages
COPY renderer/Texlivefile /tmp/Texlivefile
RUN xargs -a /tmp/Texlivefile tlmgr install && \
    tlmgr path add

# Image doesn't come with Python, so we need to install it
RUN apk add --no-cache python3 py3-pip
# Versions of the last known-good image (pydantic, starlette and anyio come in as
# dependencies of these two; pin them too so a rebuild is reproducible).
RUN pip install --break-system-packages --no-cache-dir \
    fastapi==0.135.1 uvicorn==0.41.0 pydantic==2.12.5 starlette==0.52.1 anyio==4.12.1

RUN apk add --no-cache fontconfig
COPY geometry_diagrams/assets/fonts /usr/local/share/fonts/NunitoSans/
RUN fc-cache -fv

# API server
WORKDIR /srv
COPY renderer/app /srv/app

# Run untrusted TikZ as an unprivileged user. Warm the luaotfload font index
# as that user so the first render does not rebuild it inside the timeout.
RUN adduser -D -u 10001 renderer
USER renderer
RUN luaotfload-tool --update


EXPOSE 8001
ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
