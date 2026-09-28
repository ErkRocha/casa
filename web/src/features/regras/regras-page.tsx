import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button, Input, Select } from "@/components/ui/controls";
import { useCategoriaOpcoes, usePessoas } from "@/features/cadastros/queries";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  TIPO_MATCH_LABEL,
  useAtualizarRegra,
  useCriarRegra,
  useReaplicarRegras,
  useRegras,
  useRemoverRegra,
  useTestarRegra,
  type TipoMatch,
} from "./queries";

/**
 * Tela de regras de categorização — passo 5 da fase 5.
 *
 * As regras nascem sozinhas quando você corrige um item na revisão. Esta tela
 * existe porque regra invisível que erra, erra em silêncio para sempre: sem
 * poder ver e editar, o aprendizado da D-09 vira caixa-preta.
 */
export function RegrasPage() {
  const { data: regras = [], isLoading } = useRegras();
  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();

  const atualizar = useAtualizarRegra();
  const remover = useRemoverRegra();
  const reaplicar = useReaplicarRegras();

  const automaticas = regras.filter((r) => r.criada_por === "correcao_automatica").length;

  return (
    <>
      <NovaRegra />

      <div className="mt-14 mb-5 flex flex-wrap items-center gap-6">
        <h2 className="text-caption text-text-tertiary tracking-caps-wide font-semibold uppercase">
          Regras ativas
        </h2>
        <span className="text-body-sm text-text-tertiary">
          {regras.length} no total
          {automaticas > 0 ? ` · ${automaticas} aprendida(s) por correção` : ""}
        </span>

        <Button
          variant="secondary"
          className="ml-auto"
          disabled={reaplicar.isPending || regras.length === 0}
          onClick={() => reaplicar.mutate(undefined)}
        >
          {reaplicar.isPending ? "Reaplicando..." : "Reaplicar nos itens pendentes"}
        </Button>
      </div>

      {reaplicar.data ? (
        <p className="text-body-sm text-text-secondary bg-surface mb-5 rounded-md px-6 py-4">
          {reaplicar.data.alterados} de {reaplicar.data.avaliados} item(ns) pendente(s)
          receberam sugestão nova.
          {reaplicar.data.alterados === 0
            ? " Nenhuma regra casou com o que está em revisão."
            : ""}
        </p>
      ) : null}

      {isLoading ? (
        <div className="bg-surface-sunken animate-shimmer h-60 rounded-md" />
      ) : regras.length === 0 ? (
        <p className="text-body text-text-tertiary">
          Nenhuma regra ainda. Elas aparecem sozinhas conforme você corrige categorias na
          tela de revisão — ou cadastre a primeira acima.
        </p>
      ) : (
        <Card>
          <table className="w-full table-fixed border-collapse">
            <colgroup>
              <col />
              <col className="w-40" />
              <col className="w-95" />
              <col className="w-55" />
              <col className="w-30" />
              <col className="w-45" />
              <col className="w-40" />
            </colgroup>
            <thead>
              <tr className="border-border-faint border-b">
                <Th className="pl-6">Padrão</Th>
                <Th>Match</Th>
                <Th>Aplica categoria</Th>
                <Th>Pessoa</Th>
                <Th alinhamento="right" className="pr-6">
                  Prior.
                </Th>
                <Th>Origem</Th>
                <Th className="pr-6">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {regras.map((regra) => (
                <tr
                  key={regra.id}
                  className={cn(
                    "border-border-faint border-b last:border-b-0",
                    !regra.ativo && "opacity-50",
                  )}
                >
                  <td className="text-body-sm text-text-primary truncate py-4 pl-6 font-mono">
                    {regra.padrao}
                  </td>
                  <td className="text-body-sm text-text-tertiary py-4">
                    {TIPO_MATCH_LABEL[regra.tipo_match]}
                  </td>
                  <td className="py-4 pr-4">
                    <Select
                      className="w-full"
                      value={regra.categoria_id ?? ""}
                      onChange={(e) =>
                        atualizar.mutate({
                          id: regra.id,
                          patch: {
                            categoria_id:
                              e.target.value === "" ? null : Number(e.target.value),
                          },
                        })
                      }
                    >
                      <option value="">— nenhuma —</option>
                      {categorias.map((opcao) => (
                        <option key={opcao.id} value={opcao.id}>
                          {opcao.label}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="text-body-sm text-text-secondary py-4 pr-4">
                    {pessoas.find((p) => p.id === regra.pessoa_id)?.nome ?? "—"}
                  </td>
                  <td className="tabular text-body-sm text-text-secondary py-4 pr-6 text-right">
                    {regra.prioridade}
                  </td>
                  <td className="text-caption text-text-tertiary py-4 pl-4">
                    {regra.criada_por === "correcao_automatica" ? (
                      <span title="Nasceu de uma correção sua na tela de revisão">
                        aprendida
                        {regra.acertos > 0 ? ` · ${regra.acertos}×` : ""}
                      </span>
                    ) : (
                      "manual"
                    )}
                  </td>
                  <td className="py-4 pr-6">
                    <button
                      type="button"
                      onClick={() => remover.mutate(regra.id)}
                      className="text-body-sm text-expense cursor-pointer"
                    >
                      Remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

/** Cadastro manual, com prévia de casamento antes de salvar. */
function NovaRegra() {
  const [padrao, setPadrao] = useState("");
  const [tipoMatch, setTipoMatch] = useState<TipoMatch>("contem");
  const [categoriaId, setCategoriaId] = useState("");
  const [pessoaId, setPessoaId] = useState("");
  const [teste, setTeste] = useState("");

  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();
  const criar = useCriarRegra();
  const testar = useTestarRegra();

  const podeSalvar = padrao.trim() !== "" && (categoriaId !== "" || pessoaId !== "");

  return (
    <Card className="p-9">
      <h2 className="text-caption text-text-tertiary tracking-caps-wide mb-6 font-semibold uppercase">
        Nova regra
      </h2>

      <div className="flex flex-wrap items-end gap-4">
        <Campo label="Padrão" className="min-w-140 flex-1">
          <Input
            className="w-full font-mono"
            value={padrao}
            onChange={(e) => setPadrao(e.target.value)}
            placeholder="Zaffari"
          />
        </Campo>

        <Campo label="Match">
          <Select
            value={tipoMatch}
            onChange={(e) => setTipoMatch(e.target.value as TipoMatch)}
          >
            <option value="contem">contém</option>
            <option value="exato">exato</option>
            <option value="regex">regex</option>
          </Select>
        </Campo>

        <Campo label="Categoria" className="min-w-110">
          <Select
            className="w-full"
            value={categoriaId}
            onChange={(e) => setCategoriaId(e.target.value)}
          >
            <option value="">— nenhuma —</option>
            {categorias.map((opcao) => (
              <option key={opcao.id} value={opcao.id}>
                {opcao.label}
              </option>
            ))}
          </Select>
        </Campo>

        <Campo label="Pessoa">
          <Select value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
            <option value="">— nenhuma —</option>
            {pessoas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </Select>
        </Campo>

        <Button
          disabled={!podeSalvar || criar.isPending}
          onClick={() =>
            criar.mutate(
              {
                padrao: padrao.trim(),
                tipo_match: tipoMatch,
                categoria_id: categoriaId === "" ? null : Number(categoriaId),
                pessoa_id: pessoaId === "" ? null : Number(pessoaId),
              },
              {
                onSuccess: () => {
                  setPadrao("");
                  setCategoriaId("");
                  setPessoaId("");
                },
              },
            )
          }
        >
          Adicionar
        </Button>
      </div>

      {/* Prévia: colar uma linha real e ver se casa, antes de salvar. */}
      <div className="border-border-faint mt-8 flex flex-wrap items-end gap-4 border-t pt-6">
        <Campo label="Testar contra uma linha" className="min-w-200 flex-1">
          <Input
            className="w-full font-mono"
            value={teste}
            onChange={(e) => setTeste(e.target.value)}
            placeholder="17 MAI •••• 7704 Zaffari R$ 127,03"
          />
        </Campo>
        <Button
          variant="secondary"
          disabled={!padrao.trim() || !teste.trim()}
          onClick={() => testar.mutate({ padrao, tipo_match: tipoMatch, texto: teste })}
        >
          Testar
        </Button>
        {testar.data ? (
          <span
            className={cn(
              "text-body pb-3 font-semibold",
              testar.data.casa ? "text-income" : "text-text-tertiary",
            )}
          >
            {testar.data.casa ? "casa ✓" : "não casa"}
          </span>
        ) : null}
      </div>

      {criar.error instanceof ApiError ? (
        <p role="alert" className="text-body-sm text-expense mt-5">
          {criar.error.detail}
        </p>
      ) : null}
    </Card>
  );
}

function Campo({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col", className)}>
      <span className="text-caption text-text-tertiary tracking-label-wide mb-2 font-semibold uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}

function Th({
  children,
  alinhamento = "left",
  className,
}: {
  children: React.ReactNode;
  alinhamento?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "text-label text-text-tertiary tracking-caps-wide py-4 font-semibold uppercase",
        alinhamento === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}
