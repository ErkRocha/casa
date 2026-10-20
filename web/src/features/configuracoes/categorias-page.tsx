import { useMemo, useState } from "react";

import { CabecalhoBloco, Card } from "@/components/ui/card";
import { BotaoIcone, Button, Input, Select, SelectSobreposto, Selo } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { useCategoriaArvore, useGruposDeCategoria, usePessoas } from "@/features/cadastros/queries";
import type { CategoriaArvore } from "@/features/cadastros/types";
import { corDaCategoria } from "@/features/filters/baldes";
import type { TipoTransacao } from "@/features/filters/types";
import { useCriarRegra, useReaplicarRegras, useRegras, useRemoverRegra, type Regra } from "@/features/regras/queries";
import { ApiError } from "@/lib/api";
import { competenciaDe, diaEMes, nomeDoMes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Campo, ErroDoFormulario } from "./formulario";
import { useCategoriasPluggy, useCriarCategoria, useTraduzirCategoriaPluggy, useUsoCategorias } from "./queries";
import type { CategoriaPluggyUso } from "./types";

/**
 * Categorias (`CategoriasDesktop`; D-22): a árvore com quantos lançamentos
 * cada uma tem no mês, as regras que o sistema aprendeu das correções (D-09)
 * e a tradução das categorias que o banco envia (D-21).
 */
export function CategoriasPage() {
  const [novaAberta, setNovaAberta] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  return (
    <div className="flex max-w-[1100px] flex-col gap-7 md:gap-8">
      <header className="flex flex-wrap items-center gap-6">
        <div className="flex flex-[1_1_auto] flex-col gap-2">
          <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">
            Categorias
          </h1>
          <p className="text-corpo text-texto-2 m-0">
            Cada correção que você faz vira uma regra, e o sistema aprende para os próximos
            lançamentos.
          </p>
        </div>
        <Button onClick={() => setNovaAberta(true)} className="text-corpo">
          Nova categoria
        </Button>
      </header>

      <p role="status" className="text-apoio text-texto-apoio m-0 empty:hidden">
        {aviso}
      </p>

      <div className="flex flex-col items-start gap-7 md:gap-8 lg:flex-row">
        <Arvore />
        <div className="flex w-full min-w-0 flex-col gap-7 md:gap-8 lg:flex-[2_1_480px]">
          <Regras onAviso={setAviso} />
          <TraducaoDoBanco onAviso={setAviso} />
        </div>
      </div>

      <NovaCategoria aberta={novaAberta} onFechar={() => setNovaAberta(false)} />
    </div>
  );
}

function Arvore() {
  const mes = competenciaDe(new Date());
  const arvore = useCategoriaArvore();
  const uso = useUsoCategorias(mes);
  const quantos = new Map((uso.data?.categorias ?? []).map((c) => [c.categoria_id, c.lancamentos]));

  return (
    <Card className="flex w-full min-w-0 flex-col px-8 py-9 md:px-10 lg:flex-[1_1_320px]">
      <CabecalhoBloco
        titulo="Suas categorias"
        direita={`lançamentos em ${nomeDoMes(Number(mes.slice(5, 7)))}`}
        className="pb-4"
      />
      {arvore.isLoading ? (
        <div className="bg-superficie-2 animate-shimmer rounded-interno h-80" />
      ) : arvore.isError ? (
        <p className="text-apoio text-texto-2 m-0">Não foi possível carregar as categorias.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {(arvore.data ?? []).map((raiz) => (
            <Raiz key={raiz.id} raiz={raiz} quantos={quantos} />
          ))}
          {uso.data && uso.data.sem_categoria > 0 ? (
            <li className="linha-acima text-corpo text-texto-2 flex min-h-20 items-center justify-between">
              <span className="pl-10">Sem categoria</span>
              <span className="text-apoio">{uso.data.sem_categoria}</span>
            </li>
          ) : null}
        </ul>
      )}
    </Card>
  );
}

function Raiz({ raiz, quantos }: { raiz: CategoriaArvore; quantos: Map<number, number> }) {
  const cor = corDaCategoria(raiz.cor);
  return (
    <>
      <LinhaDaArvore nome={raiz.nome} cor={cor} quantos={quantos.get(raiz.id) ?? 0} raiz inativa={!raiz.ativo} />
      {raiz.subcategorias.map((sub) => (
        <LinhaDaArvore
          key={sub.id}
          nome={sub.nome}
          cor={corDaCategoria(sub.cor ?? raiz.cor)}
          quantos={quantos.get(sub.id) ?? 0}
          inativa={!sub.ativo}
        />
      ))}
    </>
  );
}

function LinhaDaArvore({
  nome,
  cor,
  quantos,
  raiz = false,
  inativa = false,
}: {
  nome: string;
  cor: string;
  quantos: number;
  raiz?: boolean;
  inativa?: boolean;
}) {
  return (
    <li
      className={cn(
        "linha-acima text-corpo flex min-h-20 items-center justify-between",
        !raiz && "pl-11",
        inativa && "text-texto-inativo",
      )}
    >
      <span className={cn("flex items-center gap-5", raiz ? "font-forte" : "font-normal")}>
        <span aria-hidden className="inline-block size-5 rounded-[3px]" style={{ background: cor }} />
        {nome}
        {inativa ? <span className="sr-only"> (inativa)</span> : null}
      </span>
      <span className="text-apoio text-texto-2">{quantos}</span>
    </li>
  );
}

function Regras({ onAviso }: { onAviso: (texto: string) => void }) {
  const regras = useRegras();
  const remover = useRemoverRegra();
  const reaplicar = useReaplicarRegras();
  const { data: grupos } = useGruposDeCategoria();
  const { data: pessoas = [] } = usePessoas();
  const [busca, setBusca] = useState("");
  const [novaAberta, setNovaAberta] = useState(false);

  const nomeDaCategoria = useMemo(
    () => new Map(grupos.flatMap((g) => g.opcoes.map((o) => [o.id, o.nome] as const))),
    [grupos],
  );
  const termo = busca.trim().toLowerCase();
  const lista = (regras.data ?? []).filter((r) => {
    if (!termo) return true;
    const destino = r.categoria_id ? (nomeDaCategoria.get(r.categoria_id) ?? "") : "";
    return r.padrao.toLowerCase().includes(termo) || destino.toLowerCase().includes(termo);
  });

  function destinoDe(r: Regra): string {
    const partes = [
      r.categoria_id ? (nomeDaCategoria.get(r.categoria_id) ?? `Categoria ${r.categoria_id}`) : null,
      r.pessoa_id ? (pessoas.find((p) => p.id === r.pessoa_id)?.nome ?? null) : null,
    ].filter(Boolean);
    return partes.join(", ") || "—";
  }

  return (
    <Card className="flex flex-col gap-1 px-8 py-9 md:px-11">
      <div className="flex flex-wrap items-center justify-between gap-5 pb-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-bloco-celular md:text-bloco font-forte m-0">Regras que o sistema aprendeu</h2>
          <span className="text-apoio text-texto-2">Usadas antes de qualquer outra sugestão</span>
        </div>
        <label className="bg-superficie-2 rounded-botao text-texto-2 flex min-h-22 flex-[0_1_240px] items-center gap-4 px-6">
          <Icone nome="busca" tamanho={16} />
          <span className="sr-only">Buscar regra</span>
          <input
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar regra"
            className="text-apoio text-texto placeholder:text-texto-2 min-w-0 flex-1 border-none bg-transparent outline-none"
          />
        </label>
      </div>

      {regras.isLoading ? (
        <div className="bg-superficie-2 animate-shimmer rounded-interno h-60" />
      ) : regras.isError ? (
        <p className="text-apoio text-texto-2 m-0">Não foi possível carregar as regras.</p>
      ) : lista.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0 py-4">
          {termo ? "Nenhuma regra com esse texto." : "Nenhuma regra ainda: corrija uma categoria e ela nasce aqui."}
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {lista.map((r) => (
            <li
              key={r.id}
              className="linha-acima grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-2 py-6 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_160px_44px]"
            >
              <span className="flex min-w-0 flex-col gap-1">
                <span className="text-apoio text-texto-2">
                  Quando a descrição {r.tipo_match === "exato" ? "for" : r.tipo_match === "regex" ? "casar com" : "tiver"}
                </span>
                <span className="text-corpo truncate font-semibold" title={r.padrao}>
                  {r.padrao}
                </span>
              </span>
              <span className="col-start-1 row-start-2 flex flex-col gap-1 md:col-start-auto md:row-start-auto">
                <span className="text-apoio text-texto-2">vai para</span>
                <span className="text-corpo font-semibold">{destinoDe(r)}</span>
              </span>
              <span className="text-apoio text-texto-2 col-start-1 row-start-3 md:col-start-auto md:row-start-auto md:text-right">
                {usoDaRegra(r)}
              </span>
              <BotaoIcone
                rotulo={`Apagar a regra ${r.padrao}`}
                disabled={remover.isPending}
                onClick={() => {
                  if (window.confirm(`Apagar a regra "${r.padrao}"? Ela para de ser usada nas próximas importações.`)) {
                    remover.mutate(r.id, { onSuccess: () => onAviso(`Regra "${r.padrao}" apagada.`) });
                  }
                }}
                className="text-texto-2 col-start-2 row-start-1 justify-self-end bg-transparent md:col-start-auto md:row-start-auto"
              >
                <Icone nome="lixeira" tamanho={16} />
              </BotaoIcone>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-5 pt-5">
        <Button variant="secondary" onClick={() => setNovaAberta(true)}>
          Nova regra
        </Button>
        <Button
          variant="ghost"
          disabled={reaplicar.isPending}
          onClick={() =>
            reaplicar.mutate(undefined, {
              onSuccess: (r) =>
                onAviso(
                  r.alterados === 0
                    ? `Nenhum dos ${r.avaliados} itens da revisão mudou.`
                    : `${r.alterados} de ${r.avaliados} itens da revisão ganharam sugestão nova.`,
                ),
            })
          }
        >
          {reaplicar.isPending ? "Aplicando..." : "Aplicar as regras na revisão"}
        </Button>
      </div>

      <NovaRegra aberta={novaAberta} onFechar={() => setNovaAberta(false)} onAviso={onAviso} />
    </Card>
  );
}

/** "confirmada 14 vezes", ou quando nasceu se nunca foi confirmada. */
function usoDaRegra(r: Regra): string {
  if (r.acertos > 0) return `confirmada ${r.acertos} ${r.acertos === 1 ? "vez" : "vezes"}`;
  const dia = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const criada = new Date(r.criado_em);
  const dias = Math.round((dia(new Date()) - dia(criada)) / 86_400_000);
  if (dias === 0) return "criada hoje";
  if (dias === 1) return "criada ontem";
  const iso = `${criada.getFullYear()}-${String(criada.getMonth() + 1).padStart(2, "0")}-${String(criada.getDate()).padStart(2, "0")}`;
  return `criada em ${diaEMes(iso)}`;
}

function NovaRegra({
  aberta,
  onFechar,
  onAviso,
}: {
  aberta: boolean;
  onFechar: () => void;
  onAviso: (texto: string) => void;
}) {
  return (
    <Dialogo aberto={aberta} onFechar={onFechar} titulo="Nova regra">
      <FormularioRegra onFechar={onFechar} onAviso={onAviso} />
    </Dialogo>
  );
}

function FormularioRegra({ onFechar, onAviso }: { onFechar: () => void; onAviso: (t: string) => void }) {
  const [padrao, setPadrao] = useState("");
  const [categoria, setCategoria] = useState("");
  const { data: grupos } = useGruposDeCategoria();
  const criar = useCriarRegra();

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate(
          { padrao: padrao.trim(), tipo_match: "contem", categoria_id: Number(categoria), pessoa_id: null },
          {
            onSuccess: () => {
              onAviso(`Regra "${padrao.trim()}" criada.`);
              onFechar();
            },
          },
        );
      }}
    >
      <Campo rotulo="Quando a descrição tiver">
        <Input value={padrao} onChange={(e) => setPadrao(e.target.value)} required className="w-full" placeholder="Ex.: SUPERMERCADO CENTRO" />
      </Campo>
      <Campo rotulo="Vai para">
        <Select value={categoria} onChange={(e) => setCategoria(e.target.value)} required className="w-full">
          <option value="" disabled>
            Escolha a categoria
          </option>
          {grupos.map((g) => (
            <optgroup key={g.raizId} label={g.raizNome}>
              {g.opcoes.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.nome}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
      </Campo>
      {criar.error ? <ErroDoFormulario erro={criar.error} /> : null}
      <div className="flex justify-end gap-4">
        <Button variant="secondary" onClick={onFechar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!padrao.trim() || !categoria || criar.isPending}>
          {criar.isPending ? "Salvando..." : "Criar regra"}
        </Button>
      </div>
    </form>
  );
}

function TraducaoDoBanco({ onAviso }: { onAviso: (texto: string) => void }) {
  const lista = useCategoriasPluggy();
  const traduzir = useTraduzirCategoriaPluggy();
  const { data: grupos } = useGruposDeCategoria();

  return (
    <Card className="flex flex-col gap-1 px-8 py-9 md:px-11">
      <div className="flex flex-col gap-1 pb-4">
        <h2 className="text-bloco-celular md:text-bloco font-forte m-0">Categorias que o banco envia</h2>
        <span className="text-apoio text-texto-2">
          Quando nenhuma regra serve, o sistema usa esta tradução
        </span>
      </div>
      {lista.isLoading ? (
        <div className="bg-superficie-2 animate-shimmer rounded-interno h-60" />
      ) : lista.isError ? (
        <Falha titulo="Não foi possível ler as categorias do banco" erro={lista.error} onTentar={() => void lista.refetch()} />
      ) : (lista.data ?? []).length === 0 ? (
        <p className="text-apoio text-texto-2 m-0 py-4">
          Nenhuma categoria ainda: elas aparecem depois da primeira sincronização com o banco.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {(lista.data ?? []).map((linha) => (
            <li
              key={linha.pluggy_categoria_id}
              className="linha-acima grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-3 py-5.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_110px]"
            >
              <span className="text-corpo min-w-0 truncate" title={linha.pluggy_categoria_id}>
                {linha.pluggy_categoria_nome || linha.pluggy_categoria_id}
              </span>
              <span className="text-apoio text-texto-2 text-right md:order-3">
                {linha.transacoes} {linha.transacoes === 1 ? "lançamento" : "lançamentos"}
              </span>
              <span className="col-span-2 md:order-2 md:col-span-1">
                <Traducao
                  key={`${linha.mapeamento_id}-${linha.categoria_id}-${linha.ativo}`}
                  linha={linha}
                  grupos={grupos}
                  ocupado={traduzir.isPending}
                  onMudar={(categoriaId) =>
                    traduzir.mutate(
                      { linha, categoriaId },
                      {
                        onSuccess: () =>
                          onAviso(
                            categoriaId === null
                              ? `"${linha.pluggy_categoria_nome}" ficou sem tradução.`
                              : `"${linha.pluggy_categoria_nome}" traduzida. Vale para as próximas sincronizações.`,
                          ),
                        onError: (e) => onAviso(e instanceof ApiError ? e.detail : "Não foi possível salvar."),
                      },
                    )
                  }
                />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Traducao({
  linha,
  grupos,
  ocupado,
  onMudar,
}: {
  linha: CategoriaPluggyUso;
  grupos: ReturnType<typeof useGruposDeCategoria>["data"];
  ocupado: boolean;
  onMudar: (categoriaId: number | null) => void;
}) {
  const ativa = linha.mapeamento_id !== null && linha.ativo !== false;
  const [escolhida, setEscolhida] = useState<number | null>(ativa ? linha.categoria_id : null);

  if (linha.transferencia) {
    return (
      <Selo tom="neutro" className="text-apoio font-normal">
        Transferência
        <span className="sr-only">: fica fora dos gastos e não tem tradução</span>
      </Selo>
    );
  }

  const nomes = new Map(grupos.flatMap((g) => g.opcoes.map((o) => [o.id, o.nome] as const)));
  const vazia = escolhida === null;
  return (
    <SelectSobreposto
      rotulo={`Tradução de ${linha.pluggy_categoria_nome}`}
      mostrar={vazia ? "Sem tradução" : (nomes.get(escolhida) ?? linha.categoria_nome ?? "Categoria")}
      value={escolhida ?? ""}
      disabled={ocupado}
      onChange={(e) => {
        const id = e.target.value === "" ? null : Number(e.target.value);
        setEscolhida(id);
        onMudar(id);
      }}
      className={cn(
        "text-apoio rounded-campo px-5 py-2.5",
        vazia
          ? "bg-atencao-fundo-2 text-atencao-texto shadow-[inset_0_0_0_1.5px_var(--color-atencao-borda-2)]"
          : "bg-superficie-2 text-texto",
      )}
    >
      <option value="">Sem tradução</option>
      {grupos.map((g) => (
        <optgroup key={g.raizId} label={`${g.raizNome}${g.tipo === "receita" ? " (receita)" : ""}`}>
          {g.opcoes.map((o) => (
            <option key={o.id} value={o.id}>
              {o.nome}
            </option>
          ))}
        </optgroup>
      ))}
    </SelectSobreposto>
  );
}

function NovaCategoria({ aberta, onFechar }: { aberta: boolean; onFechar: () => void }) {
  return (
    <Dialogo aberto={aberta} onFechar={onFechar} titulo="Nova categoria">
      <FormularioCategoria onFechar={onFechar} />
    </Dialogo>
  );
}

function FormularioCategoria({ onFechar }: { onFechar: () => void }) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<TipoTransacao>("despesa");
  const [pai, setPai] = useState("");
  const { data: arvore = [] } = useCategoriaArvore();
  const criar = useCriarCategoria();
  const raizes = arvore.filter((r) => r.tipo === tipo && r.ativo);

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate(
          { nome: nome.trim(), tipo, categoria_pai_id: pai ? Number(pai) : null },
          { onSuccess: onFechar },
        );
      }}
    >
      <Campo rotulo="Nome">
        <Input value={nome} onChange={(e) => setNome(e.target.value)} required className="w-full" />
      </Campo>
      <Campo rotulo="Tipo">
        <Select
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoTransacao);
            setPai("");
          }}
          className="w-full"
        >
          <option value="despesa">Despesa</option>
          <option value="receita">Receita</option>
        </Select>
      </Campo>
      <Campo rotulo="Dentro de (opcional)">
        <Select value={pai} onChange={(e) => setPai(e.target.value)} className="w-full">
          <option value="">Nenhuma: categoria principal</option>
          {raizes.map((r) => (
            <option key={r.id} value={r.id}>
              {r.nome}
            </option>
          ))}
        </Select>
      </Campo>
      {criar.error ? <ErroDoFormulario erro={criar.error} /> : null}
      <div className="flex justify-end gap-4">
        <Button variant="secondary" onClick={onFechar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!nome.trim() || criar.isPending}>
          {criar.isPending ? "Salvando..." : "Criar categoria"}
        </Button>
      </div>
    </form>
  );
}
