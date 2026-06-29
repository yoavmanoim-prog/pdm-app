# ── Stage 1: Build ──────────────────────────────────────────────
# Use Node.js to install packages and compile the React app
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files first so Docker caches the install step
# (if only code changes, npm install won't re-run)
COPY package*.json ./
RUN npm install

# Copy the rest of the source code and build it
COPY . .
# Optional on-site flag baked into the build. ONLY docker-compose.onsite.yml and
# release.sh pass --build-arg VITE_ONSITE=true; the cloud build (npm run build in
# CI) and the dev/staging frontends never set it, so the SPA is byte-for-byte the
# same there. When set, it points the watch/browse feature at the same-origin
# /api backend instead of the workstation's localhost:8000 vault.
ARG VITE_ONSITE=""
RUN [ -z "$VITE_ONSITE" ] || echo "VITE_ONSITE=$VITE_ONSITE" > .env.production
RUN npm run build
# After this, /app/dist contains the compiled HTML/CSS/JS files

# ── Stage 2: Serve ───────────────────────────────────────────────
# Use a lightweight nginx image — Node.js is not included here
FROM nginx:alpine

# Copy our custom nginx config (handles routing + API proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the compiled files from Stage 1 into the nginx web root
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx listens on port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
