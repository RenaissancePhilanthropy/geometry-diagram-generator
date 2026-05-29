# Build from project root: docker build -f renderer/Dockerfile .
FROM reitzig/texlive-base-luatex:latest

# Install TeX packages
COPY renderer/Texlivefile /tmp/Texlivefile
RUN tlmgr update --self && \
    xargs -a /tmp/Texlivefile tlmgr install && \
    tlmgr path add

# Image doesn't come with Python, so we need to install it
RUN apk add --no-cache python3 py3-pip
RUN pip install --break-system-packages --no-cache-dir fastapi uvicorn pydantic

RUN apk add --no-cache fontconfig
COPY assets/fonts /usr/local/share/fonts/NunitoSans/
RUN fc-cache -fv

# API server
WORKDIR /srv
COPY renderer/app /srv/app


EXPOSE 8001
ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
