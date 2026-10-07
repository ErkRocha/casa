# Painel (D-19). Multi-stage:
#
#   deps  -> `npm ci` com o lockfile, uma camada só para as dependências;
#   dev   -> Vite com recarga (docker-compose.dev.yml, `make dev`);
#   build -> `npm run build` (typecheck + vite build) gera o dist;
#   final -> nginx só com o dist e a configuração. É o alvo padrão (`make up`).
#
# Node não entra na imagem final: ela não tem node_modules nem código-fonte.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:1.30.5-alpine
# O template vira /etc/nginx/conf.d/default.conf na subida (envsubst da
# imagem oficial), no lugar do default.conf de exemplo dela.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/snippets/ /etc/nginx/snippets/
COPY --chmod=755 nginx/hosts-permitidos.sh /docker-entrypoint.d/15-hosts-permitidos.sh
COPY --from=build /app/dist /usr/share/nginx/html

# Padrões seguros; o compose sobrescreve se precisar.
ENV API_UPSTREAM=http://api:8000 \
    WEB_ALLOWED_HOSTS=.ts.net

EXPOSE 5173
