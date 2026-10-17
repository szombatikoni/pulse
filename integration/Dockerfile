# A CQL-próba Node-futtatója (fordítókliens és motor).
# A függőségek a package-lock.json szerint, pontos verzióval települnek
# (/app/node_modules). A próba fájljai futáskor a /app/work alá kerülnek
# (docker-compose kötet), így a Node a szülőmappában találja a csomagokat.
FROM node:24.21.0-alpine3.24

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

WORKDIR /app/work
