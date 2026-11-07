# Redesign do painel (D-24)

Telas aprovadas pelo usuário, desenhadas no Claude Design. Cada `.dc.html` é o
código-fonte de uma prancheta: leia como especificação. O layout e os estilos
estão inline em cada elemento; as listas usam `<sc-for list="{{x}}">` com os dados
de exemplo no `renderVals()` do script no fim do arquivo. Eles não abrem sozinhos
no navegador (dependem do runtime do editor). **Os valores são ilustrativos**; na
implementação tudo vem da API.

## Telas

| Tela | Celular | Computador |
|---|---|---|
| Início | InicioCelular | InicioDesktop |
| Lançamentos | LancamentosCelular | LancamentosDesktop |
| Revisar | RevisarCelular | RevisarDesktop |
| Análises | AnalisesCelular | AnalisesDesktop |
| Relatórios do mês | RelatoriosCelular | RelatoriosDesktop |
| Contas e cartões | (derivar do computador) | ContasDesktop |
| Categorias | (derivar do computador) | CategoriasDesktop |
| Sincronização | (derivar do computador) | SincronizacaoDesktop |

## Tokens

Cores:
- fundo da página `#EEF1F6`; superfície (blocos) `#FFFFFF`; superfície interna `#F4F6FA`
- texto `#172033`; texto secundário `#556070` (nunca mais claro que isso em texto); texto de apoio em tabelas `#2C364A`
- linhas `#E2E6EE` (fortes) e `#EEF1F6` (entre linhas)
- destaque (azul) `#1F4FBF`, hover `#163A8F`, fundo de destaque `#EAF0FD`
- receita/positivo `#1C7A55`, fundo `#E3F3EC`, texto sobre ele `#145C40`
- atenção (âmbar) fundo `#FFF3D6` / `#FFF8E8`, texto `#5C3D00`, selo sólido `#8A5A00`, borda tracejada `#C99A3A`/`#E5C27A`
- orçamento: até 90% azul `#1F4FBF`; 90–100% `#C98A12`; estourado `#B4540A`
- pessoas (diferem por claridade, não só tom): Erik `#1E3A8A`, Laura `#6F93E6`, Juntos `#B9C2D0`

Séries de gráfico (D-29): Okabe-Ito adaptada para o fundo branco. Validada com
o validador de paleta da skill `dataviz` (`--pairs all`, superfície `#FFFFFF`):
todas com contraste de pelo menos 3:1, separação em deuteranopia, protanopia e
tritanopia de ΔE ≥ 8 e, em visão normal, ΔE ≥ 15 entre qualquer par.
- cartões, por ordem estável (ligados à Pluggy primeiro, depois por id; o 5º
  repete a 1ª): `serie-1` azul `#0068A8`, `serie-2` vermelhão `#D55E00`,
  `serie-3` violeta `#8040F0`, `serie-4` magenta `#C2185B`
- Pix `serie-pix` verde-água `#1B998B`; Débito `serie-debito` `#3A4456`;
  Boleto e Outros `serie-boleto`/`serie-outros` `#7A8699`. Os cinzas não
  disputam cor: o rótulo direto no fim da linha os distingue
- soma das selecionadas `serie-soma` `#172033`
- linha 2px; pendente = ponto vazado; futuro (até o vencimento) = tracejado;
  ciclo de fatura anterior = mesma cor com opacidade menor
- texto nunca na cor da série: a cor fica na marca (linha, bolinha do chip)

Tipografia: **Bricolage Grotesque** (pesos 400–700) em tudo, com
`font-variant-numeric: tabular-nums` na raiz. Hierarquia: título de página 26px/700
(celular 24px), título de bloco 17–18px/650, corpo 15–16px, apoio 13–14px.
Sem caixa alta em rótulos, sem fonte monoespaçada em dados.

Formas: blocos com raio 20px; elementos internos 12px; selos 6px; pílulas 999px.
Alvos de toque de no mínimo 44px. Separação entre linhas por `box-shadow: inset 0 1px 0`.

## Navegação

- Computador (≥ 1024px): barra lateral branca, três grupos sem rótulo, separados por espaço:
  1. Início, Lançamentos, Revisar (com contador)
  2. Análises, Relatórios do mês
  3. Contas e cartões, Categorias, Sincronização
  (Algumas pranchetas antigas mostram o grupo 3 sem Sincronização: vale a versão com os três.)
- Celular (< 768px): barra inferior fixa com Início, Lançamentos, Revisar (contador), Análises.
  As telas de configuração ficam acessíveis por um item "Mais" ou pelo topo; decidir na implementação
  sem criar padrão visual novo.
