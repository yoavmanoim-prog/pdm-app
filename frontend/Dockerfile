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
