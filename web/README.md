# web/ — painel

React + Vite + TypeScript + Tailwind v4 + shadcn/ui, Recharts para gráfico e
TanStack Query para dados.

O design vem do Claude Design (D-15): projeto
`Sistema de Controle Financeiro Pessoal`, arquivo `Sistema Financeiro.dc.html`.
O HTML de lá é protótipo — a fonte da verdade do *visual*, não do *código*.
Nada de markup copiado.

---

## Design tokens

Tudo em `src/styles/`:

| Arquivo | O que tem |
|---|---|
| `tokens.css` | `@theme` do Tailwind: cor (modo claro), tipografia, espaçamento, raio, sombra, geometria de gráfico |
| `theme.css` | Sobrescritas do modo escuro + camada base + utilitários |
| `chart-palette.ts` | Ponte dos tokens de cor para o Recharts e regra de cor por entidade |
| `index.css` | Único ponto de entrada: Tailwind + fontes + os dois acima |

Três coisas que não são óbvias:

**A escala de espaçamento é de 2px, não 4px.** `--spacing: 2px`, porque o
protótipo anda de dois em dois (10px, 14px, 18px, 22px). Isso reproduz o
design exatamente, mas **um utilitário vale metade do px habitual do
Tailwind**: `p-4` é 8px, `gap-9` é 18px, `w-104` é 208px.

**O modo escuro não é inversão automática.** São passos escolhidos, copiados
de `buildTheme('dark')`. Só variáveis de cor mudam; tipografia, espaçamento e
raio são compartilhados. Nenhum componente lê o tema — a classe `.dark` no
`<html>` troca as variáveis e pronto.

**Tamanho de texto tem nome de papel, não de tamanho.** `text-caption`,
`text-body`, `text-display`. O protótipo usa meios-pixels (11.5px, 12.5px), e
nomear por papel evita `text-[12.5px]` espalhado.

---

## Telas

```
features/
  filters/     estado de filtro compartilhado pelas duas telas + barra e chips
  cadastros/   queries de pessoas, categorias e formas de pagamento
  transacoes/  fase 3: tabela densa, edição inline, ação em lote, drawer
  analytics/   fase 4: cinco painéis
```

**O filtro é um só.** `FilterProvider` vive acima do roteamento em `main.tsx`,
então trocar de Transações para Analytics mantém o recorte. `filtrosParaQuery`
converte o estado nos mesmos parâmetros de URL para as duas telas — a API tem
uma função `montar_filtros` só, do outro lado.

**Nada é filtrado ou somado no navegador** (D-14). Todo filtro vira query
string; total, percentual, média e delta chegam prontos da API. A única
aritmética no front é geometria (largura de barra, teto de eixo) e formatação.

**Dinheiro chega como string.** `numeric(12,2)` virando `number` em JS perde
centavo em algum ponto. `toNumero()` só é chamado para medir uma barra ou
formatar — nunca para somar.

## Analytics

`src/features/analytics/`. Cinco painéis, espelhando a fase 4 do roadmap.

```
analytics-page.tsx            grade 2 colunas, estado do drill-down
types.ts                      espelho do JSON de /analytics/resumo
queries.ts                    um endpoint só para os cinco painéis
components/
  panel.tsx                   moldura de painel
  monthly-evolution-chart.tsx Recharts — barras empilhadas por pessoa
  category-composition-chart.tsx  tabela-medidor com drill-down
  person-split-chart.tsx      barra 100% + placares
  budget-progress-chart.tsx   medidores com marca de ritmo
  period-comparison-cards.tsx placares
  chart-tooltip.tsx           tooltip compartilhada
```

**Só um painel é Recharts.** Evolução mensal é série temporal de magnitude —
gráfico de verdade. Os outros quatro são medidores e placares: barra de
progresso e número grande não viram SVG só para usar a biblioteca. Eles ficam
em HTML semântico (`<table>`, `<dl>`), o que dá texto selecionável, leitura
por leitor de tela e o vão de 2px entre segmentos de graça.

**Nenhum componente calcula.** Total, percentual, média e delta chegam
prontos nos tipos de `types.ts`. Agregação é do banco (D-14). A única conta
que sobrou é geometria de eixo (`niceMax`), que é apresentação.

---

## Duas correções conscientes em cima do protótipo

**1. Cor de categoria seguia o ranking.** O protótipo chamava
`monoColor(idx, total)` com `idx` = posição da categoria na lista já ordenada
por valor. Consequência: mudar o filtro reordenava as barras e repintava todas
as categorias sobreviventes — a mesma categoria trocava de cor entre dois
estados da mesma tela. Agora a cor mora em `categorias.cor` no banco (token
`cat-1`..`cat-9`, semeado pelo `seed.py`) e chega junto de cada linha da API.
Mesma aparência, cor amarrada à entidade.

**2. Realce do mês em curso.** O protótipo pinta um retângulo `accentSoft`
atrás da coluna do mês corrente. Não há jeito estável de fazer isso no
Recharts sem depender de interno da biblioteca, então o sinal virou rótulo do
mês em negrito e na cor primária, mais uma nota sob o gráfico. Mesma
informação, sem gambiarra.

---

## Uma ressalva de acessibilidade, para decidir no Claude Design

As três séries de pessoa são uma matiz só (205), variando em L e C. Distância
entre pares adjacentes na pilha A → B → Conjunto, em ΔE OKLab ×100:

| | A–B | B–C | A–C |
|---|---|---|---|
| claro | 34.0 | **12.4** | 27.9 |
| escuro | 20.0 | 16.6 | 11.2 |

O piso de visão normal é 15. **B–Conjunto no modo claro fica em 12.4** — dois
azuis próximos demais para separar só pela cor. Mitigação já presente: toda
série de pessoa vem rotulada em texto (legenda, placares, tooltip, rótulo
dentro da barra), então identidade nunca depende da cor sozinha.

Ainda assim vale reabrir esse par no Claude Design. O ajuste mais barato é
escurecer `personB` no modo claro (de `L 0.4` para ~`L 0.32`), o que leva o
par para ~ΔE 18 sem mexer no resto da paleta.

> Medido à mão a partir dos valores OKLCH (OKLCH já é OKLab polar, a distância
> é direta). O validador de paleta do skill `dataviz` não rodou: **não há Node
> instalado nesta máquina**. Quando o container do front subir, vale rodar lá.

---

## Estado atual

Transações e Analytics estão ligadas na API. Orçamentos e Relatórios seguem
como "em breve" na sidebar — o CRUD de orçamento existe na API
(`POST /orcamentos`), mas sem tela própria ainda.

Verificado com Node 24 / npm 11:

- `npx tsc --noEmit` passa sem erro;
- `npm run build` gera o bundle;
- `npm run dev` sobe e **todos** os módulos de `src/` transformam sem erro;
- CORS do dev server (`localhost:5173`) é aceito pela API.

O que **não** foi verificado: renderização em navegador. Ninguém abriu a tela
para conferir layout, interação ou o gráfico desenhado — compila e serve não é
o mesmo que está bonito e funciona ao clique.
