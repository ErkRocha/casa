#!/bin/sh
# Gera o `map` de hosts aceitos pelo nginx a partir de WEB_ALLOWED_HOSTS (D-19).
#
# Roda na subida do container, em /docker-entrypoint.d/ (antes do envsubst do
# template). Mesmo formato do Vite: lista separada por vírgula; entrada que
# começa com ponto aceita o domínio e os subdomínios (".ts.net"). localhost,
# 127.0.0.1 e [::1] entram sempre. Vazio: só eles.
#
# Entrada com caractere fora de [a-z0-9.-] é ignorada com aviso: o valor vira
# configuração do nginx, e não pode carregar sintaxe dele.
set -eu

DESTINO="${HOSTS_MAP:-/etc/nginx/hosts_permitidos.map}"
LISTA="${WEB_ALLOWED_HOSTS-.ts.net}"

{
  echo "# Gerado por hosts-permitidos.sh a partir de WEB_ALLOWED_HOSTS."
  echo "localhost 1;"
  echo "127.0.0.1 1;"
  echo "\"[::1]\" 1;"

  echo "$LISTA" | tr ',' '\n' | while IFS= read -r host; do
    host="$(echo "$host" | tr -d ' \t\r' | tr 'A-Z' 'a-z')"
    [ -n "$host" ] || continue
    case "$host" in
      *[!a-z0-9.-]*)
        echo "hosts-permitidos: ignorando '$host' (caractere inválido)" >&2
        continue
        ;;
    esac
    case "$host" in
      .*)
        dominio="${host#.}"
        [ -n "$dominio" ] || continue
        escapado="$(echo "$dominio" | sed 's/\./\\./g')"
        echo "\"~^(.+\\.)?${escapado}\$\" 1;"
        ;;
      *)
        echo "$host 1;"
        ;;
    esac
  done
} >"$DESTINO"

echo "hosts-permitidos: $(grep -c ' 1;$' "$DESTINO") entrada(s) em $DESTINO" >&2
