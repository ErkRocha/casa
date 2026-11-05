#!/usr/bin/env bash
# Conferência geral da casa, SÓ LEITURA: containers, health das APIs, última
# sync do agendador, servidor MCP, túnel do ngrok e tailscale serve.
#
# Chamado por `make conferir`. Uma linha por item: OK, AVISO ou FALHA.
# Nunca imprime o token do MCP nem endereços (ngrok, tailnet).
# Sai com 1 se houver alguma FALHA.

set -uo pipefail
cd "$(dirname "$0")/.."

WEB="http://127.0.0.1:${WEB_PORT:-5173}"
MCP_DIR="${MCP_DIR:-../mcp-servidor}"
MCP_PORT="${MCP_PORT:-8765}"
NGROK_API="http://127.0.0.1:4040/api/tunnels"
TAILSCALE="${TAILSCALE:-tailscale}"
if ! command -v "$TAILSCALE" >/dev/null 2>&1 && [ -x "/c/Program Files/Tailscale/tailscale.exe" ]; then
    TAILSCALE="/c/Program Files/Tailscale/tailscale.exe"
fi

FALHAS=0
AVISOS=0
linha() {
    printf '%-6s %s\n' "$1" "$2"
    case "$1" in FALHA) FALHAS=$((FALHAS + 1)) ;; AVISO) AVISOS=$((AVISOS + 1)) ;; esac
}

# --- containers -------------------------------------------------------------
for c in casa_db casa_api casa_web casa_compras casa_agendador; do
    est="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null)"
    est="${est% }"
    case "$est" in
        running|"running healthy") linha OK "container $c: $est" ;;
        "running starting") linha AVISO "container $c: subindo agora (rode de novo em 1 min)" ;;
        "") linha FALHA "container $c: não existe (make up)" ;;
        *) linha FALHA "container $c: $est (veja: docker logs $c)" ;;
    esac
done

# --- health -----------------------------------------------------------------
health() { # rótulo caminho
    local corpo codigo
    corpo="$(curl -s -m 5 -w ' %{http_code}' "$WEB$2" 2>/dev/null)"
    codigo="${corpo##* }"
    if [ "$codigo" = 200 ] && [[ "$corpo" == *'"status":"ok"'* ]]; then
        linha OK "$1: ok"
    elif [ "$codigo" = 000 ] || [ -z "$codigo" ]; then
        linha FALHA "$1: sem resposta em $WEB (containers no ar? make up)"
    else
        linha FALHA "$1: HTTP $codigo (${corpo% *})"
    fi
}
health "/api/health" "/api/health"
health "/api/compras/health" "/api/compras/health"

# --- agendador --------------------------------------------------------------
logs_ag="$(docker logs casa_agendador 2>&1)"
ultima="$(grep 'sync: ' <<<"$logs_ag" | tail -1)"
proxima="$(grep 'próxima sync em' <<<"$logs_ag" | tail -1 | sed 's/.*próxima sync em //')"
if [ -z "$ultima" ]; then
    linha AVISO "agendador: nenhuma sync desde que o container subiu; próxima ${proxima:-?}"
else
    quando="${ultima:0:16}"   # dd/mm/aaaa hh:mm
    iso="${quando:6:4}-${quando:3:2}-${quando:0:2} ${quando:11:5}"
    idade_h=$(( ( $(date +%s) - $(date -d "$iso" +%s 2>/dev/null || date +%s) ) / 3600 ))
    resumo="${ultima#*sync: }"
    if [[ "$ultima" == *"sync: ok"* && "$ultima" != *"erros:"* ]]; then
        if [ "$idade_h" -gt 26 ]; then
            linha FALHA "agendador: última sync há ${idade_h} h ($quando): atrasada; próxima ${proxima:-?}"
        else
            linha OK "agendador: última sync $quando: $resumo; próxima ${proxima:-?}"
        fi
    elif [[ "$ultima" == *"começando"* ]]; then
        linha AVISO "agendador: sync começou em $quando e ainda não terminou"
    else
        linha FALHA "agendador: última sync $quando: $resumo"
    fi
fi

# --- servidor MCP -----------------------------------------------------------
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"conferir","version":"1"}}}'
TOKEN=""
if [ -f "$MCP_DIR/.env" ]; then
    TOKEN="$(sed -n 's/^MCP_TOKEN=//p' "$MCP_DIR/.env" | tr -d '\r"'"'"' ')"
fi
mcp_codigo() { # base_url -> código HTTP do initialize no caminho secreto
    curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST "$1/mcp-$TOKEN" \
        -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
        -H 'ngrok-skip-browser-warning: 1' --data "$INIT" 2>/dev/null
}
if [ -z "$TOKEN" ]; then
    codigo="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$MCP_PORT/" 2>/dev/null)"
    if [ "$codigo" = 000 ]; then
        linha FALHA "servidor MCP: nada na porta $MCP_PORT (rode iniciar-tudo.bat no mcp-servidor)"
    else
        linha AVISO "servidor MCP: porta $MCP_PORT responde, mas sem $MCP_DIR/.env para testar o MCP"
    fi
else
    codigo="$(mcp_codigo "http://127.0.0.1:$MCP_PORT")"
    case "$codigo" in
        200) linha OK "servidor MCP: responde ao initialize na porta $MCP_PORT" ;;
        000) linha FALHA "servidor MCP: nada na porta $MCP_PORT (rode iniciar-tudo.bat no mcp-servidor)" ;;
        *) linha FALHA "servidor MCP: HTTP $codigo no initialize (veja logs\\servidor-eventos.log no mcp-servidor)" ;;
    esac
fi

# --- ngrok ------------------------------------------------------------------
tuneis="$(curl -s -m 3 "$NGROK_API" 2>/dev/null)"
publica="$(grep -o '"public_url":"https://[^"]*"' <<<"$tuneis" | head -1 | sed 's/"public_url":"//; s/"$//')"
if [ -z "$publica" ]; then
    linha FALHA "ngrok: nenhum túnel de pé (rode iniciar-tudo.bat no mcp-servidor)"
elif [ -z "$TOKEN" ]; then
    linha AVISO "ngrok: túnel de pé, mas sem token para testar o caminho até o MCP"
else
    codigo="$(mcp_codigo "$publica")"
    if [ "$codigo" = 200 ]; then
        linha OK "ngrok: túnel de pé e chega ao servidor MCP"
    else
        linha FALHA "ngrok: túnel de pé, mas o initialize por ele deu HTTP $codigo"
    fi
fi
unset TOKEN publica

# --- tailscale serve --------------------------------------------------------
if ! command -v "$TAILSCALE" >/dev/null 2>&1 && [ ! -x "$TAILSCALE" ]; then
    linha FALHA "tailscale: não instalado (winget install Tailscale.Tailscale)"
else
    estado="$("$TAILSCALE" status --json 2>/dev/null | grep -o '"BackendState": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"//')"
    serve="$("$TAILSCALE" serve status 2>&1)"
    if [ "$estado" != Running ]; then
        linha FALHA "tailscale: ${estado:-sem resposta} (abra o Tailscale e entre na conta)"
    elif [[ "$serve" == *"Funnel on"* || "$serve" == *"(Funnel"* ]]; then
        linha FALHA "tailscale serve: FUNNEL LIGADO, o painel está na internet aberta (tailscale funnel reset)"
    elif [[ "$serve" == *"proxy http://127.0.0.1:${WEB_PORT:-5173}"* ]]; then
        linha OK "tailscale serve: publica o painel só na tailnet (endereço: tailscale serve status)"
    elif [[ "$serve" == *"No serve config"* || -z "$serve" ]]; then
        linha AVISO "tailscale serve: desligado (passo b do docs/roteiro-teste-casa.md)"
    else
        linha AVISO "tailscale serve: ligado, mas não aponta para o painel (confira: tailscale serve status)"
    fi
fi

echo
if [ "$FALHAS" -eq 0 ]; then
    echo "Resumo: tudo ok${AVISOS:+ ($AVISOS aviso(s))}" | sed 's/ (0 aviso(s))//'
else
    echo "Resumo: $FALHAS falha(s), $AVISOS aviso(s)"
    exit 1
fi
