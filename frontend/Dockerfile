# Két lépcsős build: az első image-ben a Node lefordítja a frontendet statikus
# fájlokra, a második csak ezeket a fájlokat és az nginx webszervert tartalmazza.
FROM node:24-alpine AS build
WORKDIR /app

# Előbb csak a csomaglistát másoljuk, így kódváltozáskor az `npm ci` lépés a
# gyorsítótárból jön. Az `npm ci` pontosan a package-lock.json szerint telepít.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
