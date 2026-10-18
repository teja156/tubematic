FROM node:20-slim

RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    ca-certificates \
    ffmpeg \
    curl \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV REMOTION_CHROME_FLAGS="--disable-dev-shm-usage --no-sandbox"
ENV CHROMIUM_FLAGS="--disable-dev-shm-usage --no-sandbox"

WORKDIR /app

# Volume mount points. /logs and /backups are created here as well as being bind
# mounts: the e2e stack (docker-compose.test.yml) publishes neither, and a
# writable directory in the image's own layer means both work there too, just
# without persistence.
RUN mkdir -p /data /jobs /output_videos /logs /backups

# ── Remotion project ──────────────────────────────────────────
COPY renderer/remotion/package*.json ./remotion/
WORKDIR /app/remotion
RUN npm ci

COPY renderer/remotion/ .

# ── Python API server ─────────────────────────────────────────
WORKDIR /app/api
COPY renderer/api/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY renderer/api/ .

# ── MCP server ────────────────────────────────────────────────
WORKDIR /app/mcp
COPY mcp/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY mcp/ .

# ── Shared library ────────────────────────────────────────────
# /app/lib rather than /app, and the difference matters: /app also holds api/,
# mcp/ and remotion/, so putting it on the path would make all of them
# importable as a side effect — including /app/mcp, which collides by name with
# the official MCP SDK that fastmcp imports. /app/lib holds exactly one package
# and therefore has no side effects to reason about.
#
# Copied late so editing it does not invalidate the npm ci layer above.
COPY tubematic_core/ /app/lib/tubematic_core/
# Beside the package, not inside it: version.py looks for VERSION in the
# package directory's parent, which is the repo root on the host and /app/lib
# here. Same rule, both contexts.
COPY VERSION /app/lib/VERSION
ENV PYTHONPATH=/app/lib

# ── Entrypoint ────────────────────────────────────────────────
COPY renderer/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 4000
EXPOSE 4100

# One image, three services (TMDEV-87). entrypoint.sh does the shared DB
# permission setup and then execs whatever it is given, so each container runs
# exactly one foreground process. This CMD is the tubematic-api default;
# tubematic-mcp and tubematic-renderer override it via compose `command:`.
CMD ["/app/entrypoint.sh", "python3", "/app/api/server.py"]
