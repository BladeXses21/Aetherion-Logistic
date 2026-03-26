# Dockerfile — двоетапна збірка для Vue.js фронтенду (Epic 5.1)
#
# Stage 1: build — компілює TypeScript/Vue у статичні файли
# Stage 2: serve — легкий nginx:alpine для роздачі статики

# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Копіюємо залежності окремо для кешування шарів
COPY package*.json ./
RUN npm ci --quiet

# Копіюємо вихідний код та збираємо
COPY . .
RUN npm run build

# ── Stage 2: Serve ──────────────────────────────────────────────────────────
FROM nginx:alpine AS serve

# Копіюємо зібрані файли
COPY --from=build /app/dist /usr/share/nginx/html

# Копіюємо nginx конфіг для SPA (handle 404 → index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
