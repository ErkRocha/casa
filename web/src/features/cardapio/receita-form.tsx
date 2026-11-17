import { useState } from "react";

import { BotaoIcone, Button, Input, Select } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { novoIdCliente } from "@/features/compras/id-cliente";
import { useBuscaProdutos } from "@/features/compras/queries";
import { ApiError } from "@/lib/api";
import { useAdiado } from "@/lib/use-adiado";
import { cn } from "@/lib/utils";
import { useSalvarReceita } from "./queries";
import { decimalDigitado, decimalParaCampo, ROTULO_TIPO, TIPOS, UNIDADES } from "./textos";
import type {
  IngredienteEntrada,
  ReceitaCorpo,
  ReceitaDetalhe,
  TipoRefeicao,
  UnidadeMedida,
} from "./types";

/** O produto de um ingrediente: um que existe, ou um nome para criar. */
type ProdutoEscolhido = { id: number; nome: string } | { id: null; nome: string };

interface LinhaIngrediente {
  chave: string;
  produto: ProdutoEscolhido | null;
  quantidade: string;
  unidade: UnidadeMedida;
  observacao: string;
}

function linhaVazia(): LinhaIngrediente {
  return { chave: novoIdCliente(), produto: null, quantidade: "", unidade: "g", observacao: "" };
}

/**
 * Formulário da receita (`CardapioReceitaCelular`, editar e criar): nome,
 * tipo, ingredientes, rendimento, tempo, quanto dura, se congela e modo de
 * preparo. Salva com PUT (receita que existe) ou POST com `id_cliente`.
 */
export function ReceitaForm({
  inicial,
  quem,
  onSalva,
  onCancelar,
}: {
  /** Sem receita: formulário de receita nova. */
  inicial: ReceitaDetalhe | null;
  quem: string | null;
  onSalva: (receita: ReceitaDetalhe) => void;
  onCancelar: () => void;
}) {
  const [nome, setNome] = useState(inicial?.nome ?? "");
  const [tipo, setTipo] = useState<TipoRefeicao>(inicial?.tipo ?? "almoco");
  const [rendimento, setRendimento] = useState(decimalParaCampo(inicial?.rendimento_porcoes ?? "1"));
  const [tempo, setTempo] = useState(inicial?.tempo_preparo_min?.toString() ?? "");
  const [antecipar, setAntecipar] = useState(inicial?.pode_antecipar ?? false);
  const [dura, setDura] = useState(inicial?.dura_dias?.toString() ?? "");
  const [congela, setCongela] = useState(inicial?.pode_congelar ?? false);
  const [modo, setModo] = useState(inicial?.modo_preparo ?? "");
  const [linhas, setLinhas] = useState<LinhaIngrediente[]>(() =>
    inicial && inicial.ingredientes.length > 0
      ? inicial.ingredientes.map((i) => ({
          chave: String(i.id),
          produto: { id: i.produto_id, nome: i.produto_nome },
          quantidade: decimalParaCampo(i.quantidade),
          unidade: i.unidade,
          observacao: i.observacao ?? "",
        }))
      : [linhaVazia()],
  );
  const [erro, setErro] = useState<string | null>(null);
  // Um por abertura: reenviar depois de uma falha de rede não cria duas receitas.
  const [idCliente] = useState(novoIdCliente);
  const salvar = useSalvarReceita(quem ?? "");

  function mudarLinha(chave: string, parcial: Partial<LinhaIngrediente>) {
    setLinhas((atual) => atual.map((l) => (l.chave === chave ? { ...l, ...parcial } : l)));
  }

  function enviar() {
    const corpo = montarCorpo();
    if (typeof corpo === "string") {
      setErro(corpo);
      return;
    }
    setErro(null);
    salvar.mutate(
      { id: inicial?.id ?? null, idCliente, corpo },
      {
        onSuccess: onSalva,
        onError: (e) =>
          setErro(
            e instanceof ApiError
              ? e.isConflito && e.detail.startsWith("Erro ")
                ? "Já existe uma receita com esse nome."
                : e.detail
              : "Não foi possível salvar. Tente de novo.",
          ),
      },
    );
  }

  /** O corpo da API, ou o texto do que falta. */
  function montarCorpo(): ReceitaCorpo | string {
    if (!nome.trim()) return "Dê um nome à receita.";
    const rende = decimalDigitado(rendimento);
    if (rende === null || Number(rende) <= 0) return "Diga para quantas porções a receita rende.";
    if (tempo.trim() && !/^\d+$/.test(tempo.trim())) return "O tempo é em minutos, só números.";
    if (dura.trim() && !/^[1-9]\d*$/.test(dura.trim())) return "Quantos dias dura: um número inteiro, de 1 em diante.";
    if (antecipar && !dura.trim()) return "Quem pode ser feita antes precisa dizer quantos dias dura.";
    const ingredientes: IngredienteEntrada[] = [];
    for (const [i, l] of linhas.entries()) {
      const vazia = !l.produto && !l.quantidade.trim() && !l.observacao.trim();
      if (vazia) continue;
      if (!l.produto) return `Ingrediente ${i + 1}: escolha o produto.`;
      let quantidade: string | null = null;
      if (l.unidade !== "a_gosto") {
        quantidade = decimalDigitado(l.quantidade);
        if (quantidade === null || Number(quantidade) <= 0) {
          return `${l.produto.nome}: diga a quantidade (ou escolha "a gosto").`;
        }
      }
      ingredientes.push({
        ...(l.produto.id !== null ? { produto_id: l.produto.id } : { produto_nome: l.produto.nome }),
        quantidade,
        unidade: l.unidade,
        observacao: l.observacao.trim() || null,
      });
    }
    return {
      nome: nome.trim(),
      tipo,
      rendimento_porcoes: rende,
      tempo_preparo_min: tempo.trim() ? Number(tempo) : null,
      modo_preparo: modo.trim() || null,
      pode_antecipar: antecipar,
      dura_dias: dura.trim() ? Number(dura) : null,
      pode_congelar: congela,
      ingredientes,
    };
  }

  return (
    <form
      className="flex flex-col gap-8"
      onSubmit={(e) => {
        e.preventDefault();
        enviar();
      }}
    >
      <Campo rotulo="Nome">
        <Input value={nome} maxLength={120} onChange={(e) => setNome(e.target.value)} autoFocus={!inicial} />
      </Campo>

      <div className="grid grid-cols-2 gap-5">
        <Campo rotulo="Refeição">
          <Select value={tipo} onChange={(e) => setTipo(e.target.value as TipoRefeicao)}>
            {TIPOS.map((t) => (
              <option key={t} value={t}>
                {ROTULO_TIPO[t]}
              </option>
            ))}
          </Select>
        </Campo>
        <Campo rotulo="Rende (porções)">
          <Input inputMode="decimal" value={rendimento} onChange={(e) => setRendimento(e.target.value)} />
        </Campo>
        <Campo rotulo="Tempo (min)">
          <Input inputMode="numeric" value={tempo} onChange={(e) => setTempo(e.target.value)} />
        </Campo>
        <Campo rotulo="Dura (dias)">
          <Input inputMode="numeric" value={dura} onChange={(e) => setDura(e.target.value)} />
        </Campo>
      </div>

      <div className="flex flex-col gap-2">
        <Marcar marcado={antecipar} onMudar={setAntecipar}>
          Pode ser feita antes (na sessão de preparo)
        </Marcar>
        <Marcar marcado={congela} onMudar={setCongela}>
          Pode congelar
        </Marcar>
      </div>

      <section aria-label="Ingredientes" className="flex flex-col gap-5">
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-enfase font-forte m-0">Ingredientes</h3>
          <span className="text-pequeno text-texto-2">para o rendimento acima</span>
        </div>
        {linhas.map((l, i) => (
          <div key={l.chave} className="bg-superficie-2 rounded-interno flex flex-col gap-4 p-5">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <ProdutoCampo
                  rotulo={`Produto do ingrediente ${i + 1}`}
                  valor={l.produto}
                  onMudar={(produto) => mudarLinha(l.chave, { produto })}
                />
              </div>
              <BotaoIcone
                rotulo={`Tirar o ingrediente ${i + 1}`}
                className="bg-superficie"
                onClick={() => setLinhas((atual) => atual.filter((x) => x.chave !== l.chave))}
              >
                <Icone nome="lixeira" tamanho={16} />
              </BotaoIcone>
            </div>
            <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-3">
              <Input
                aria-label={`Quantidade do ingrediente ${i + 1}`}
                inputMode="decimal"
                placeholder="Qtd."
                disabled={l.unidade === "a_gosto"}
                value={l.unidade === "a_gosto" ? "" : l.quantidade}
                onChange={(e) => mudarLinha(l.chave, { quantidade: e.target.value })}
                className="bg-superficie text-right"
              />
              <Select
                aria-label={`Unidade do ingrediente ${i + 1}`}
                value={l.unidade}
                onChange={(e) => mudarLinha(l.chave, { unidade: e.target.value as UnidadeMedida })}
                className="bg-superficie"
              >
                {UNIDADES.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.rotulo}
                  </option>
                ))}
              </Select>
            </div>
            <Input
              aria-label={`Observação do ingrediente ${i + 1}`}
              placeholder="Observação (opcional): picado, da marca…"
              maxLength={300}
              value={l.observacao}
              onChange={(e) => mudarLinha(l.chave, { observacao: e.target.value })}
              className="bg-superficie"
            />
          </div>
        ))}
        <Button variant="secondary" onClick={() => setLinhas((atual) => [...atual, linhaVazia()])}>
          <Icone nome="adicionar" tamanho={16} espessura={2.4} />
          Adicionar ingrediente
        </Button>
      </section>

      <Campo rotulo="Modo de preparo">
        <textarea
          value={modo}
          maxLength={10000}
          rows={6}
          onChange={(e) => setModo(e.target.value)}
          placeholder="Um passo por linha."
          className="bg-superficie-2 text-texto placeholder:text-texto-2 text-corpo rounded-interno border-none px-7 py-5 leading-normal outline-none"
        />
      </Campo>

      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      {!quem ? <p className="text-apoio text-texto-2 m-0">Diga quem você é para salvar.</p> : null}

      <div className="flex flex-wrap gap-4">
        <Button type="submit" disabled={!quem || salvar.isPending}>
          {salvar.isPending ? "Salvando…" : inicial ? "Salvar receita" : "Criar receita"}
        </Button>
        <Button variant="ghost" onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-3">
      <span className="text-apoio font-semibold">{rotulo}</span>
      {children}
    </label>
  );
}

function Marcar({
  marcado,
  onMudar,
  children,
}: {
  marcado: boolean;
  onMudar: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-h-22 cursor-pointer items-center gap-5">
      <input
        type="checkbox"
        className="accent-destaque size-10"
        checked={marcado}
        onChange={(e) => onMudar(e.target.checked)}
      />
      <span className="text-corpo">{children}</span>
    </label>
  );
}

/**
 * O produto de um ingrediente, por busca (a mesma da lista de compras). Escolhido,
 * vira o nome com "Trocar". Produto que não existe só é criado por escolha
 * explícita ("Criar ... como produto novo"): erro de digitação não cria produto.
 */
function ProdutoCampo({
  rotulo,
  valor,
  onMudar,
}: {
  rotulo: string;
  valor: ProdutoEscolhido | null;
  onMudar: (produto: ProdutoEscolhido | null) => void;
}) {
  const [texto, setTexto] = useState("");
  const busca = useAdiado(texto, 200);
  const resultados = useBuscaProdutos(busca);

  if (valor) {
    return (
      <div className="flex min-h-22 items-center justify-between gap-3">
        <span className="text-enfase font-semibold">
          {valor.nome}
          {valor.id === null ? <span className="text-pequeno text-texto-2 font-normal"> (produto novo)</span> : null}
        </span>
        <button
          type="button"
          onClick={() => {
            setTexto("");
            onMudar(null);
          }}
          className="text-destaque text-apoio min-h-20 cursor-pointer border-none bg-transparent px-2 font-semibold"
        >
          Trocar
        </button>
      </div>
    );
  }

  const lista = texto.trim() ? (resultados.data ?? []) : [];
  return (
    <div className="flex flex-col gap-2">
      <Input
        aria-label={rotulo}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Buscar produto…"
        autoComplete="off"
        className="bg-superficie w-full"
      />
      {texto.trim() ? (
        <div role="listbox" aria-label="Produtos" className="bg-superficie rounded-interno flex flex-col">
          {lista.map((p) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={false}
              onClick={() => onMudar({ id: p.id, nome: p.nome })}
              className="text-texto flex min-h-22 cursor-pointer items-center justify-between gap-3 border-none bg-transparent px-5 text-left"
            >
              <span className="text-apoio font-semibold">{p.nome}</span>
              <span className="text-pequeno text-texto-2">{p.secao_nome}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => onMudar({ id: null, nome: texto.trim() })}
            className={cn(
              "text-destaque flex min-h-22 cursor-pointer items-center gap-3 border-none bg-transparent px-5 text-left text-[14px] font-semibold",
            )}
          >
            <Icone nome="adicionar" tamanho={14} espessura={2.4} />
            Criar "{texto.trim()}" como produto novo
          </button>
        </div>
      ) : null}
    </div>
  );
}
