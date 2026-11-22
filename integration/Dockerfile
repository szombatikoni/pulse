# A CQL-próba Node-futtatója (fordítókliens és motor), és M3-tól (K2) a motor
# hosszan futó HTTP-szolgáltatásként. Két cél (target):
#   szolgaltatas  a gyökér docker-compose.yml `cql` szolgáltatása: az ELM és a
#                 kód az image-ben, nem root felhasználóval fut;
#   futtato       az integration/docker-compose.yml egyszer lefutó parancsai.
#                 Ez az utolsó szakasz, így cél megadása nélkül (build: .) ez
#                 épül, ugyanúgy, mint korábban.
# A függőségek a package-lock.json szerint, pontos verzióval települnek
# (/app/node_modules).
FROM node:24.21.0-alpine3.24 AS fuggosegek

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

# A szolgáltatás: az ELM és a két modul az image-be kerül (root tulajdonban,
# a futó folyamat csak olvassa), a folyamat a node felhasználóval fut.
FROM fuggosegek AS szolgaltatas
COPY elm/ ./elm/
COPY motor.mjs szolgaltatas.mjs ./
USER node
ENV PORT=8080
EXPOSE 8080
CMD ["node", "szolgaltatas.mjs"]

# A próba fájljai futáskor a /app/work alá kerülnek (docker-compose kötet),
# így a Node a szülőmappában találja a csomagokat.
FROM fuggosegek AS futtato
WORKDIR /app/work
