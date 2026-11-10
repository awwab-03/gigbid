# GigBid web: build the React app, serve it with Caddy (SPA fallback)
FROM node:22-alpine AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npx vite build

FROM caddy:2.10-alpine
COPY --from=build /web/dist /srv
COPY infra/docker/Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
