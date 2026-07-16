# =========================================================================
# Maestro frontend — Next.js standalone server.
# NEXT_PUBLIC_* values are inlined at build time. They default to empty, which
# means same-origin, so one image works behind any domain. Override them only
# when the API lives on a different host than the app.
# =========================================================================

FROM node:20.20.2-bookworm-slim AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=""
ARG NEXT_PUBLIC_WS_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_WS_BASE_URL=$NEXT_PUBLIC_WS_BASE_URL

# next/font/google downloads and self-hosts the fonts here, so this step needs
# network access. An offline build would have to vendor them via next/font/local.
RUN npm run build


FROM node:20.20.2-bookworm-slim AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Keep both stages on the same libc: standalone traces native modules out of
# node_modules, and a glibc/musl mismatch only surfaces at runtime.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# No public/ copy: this repo has no such directory, and COPY would fail.

USER node

EXPOSE 3000

CMD ["node", "server.js"]
