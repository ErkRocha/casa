import { useId, useState } from "react";

import { Abas } from "@/components/ui/abas";
import { BotaoIcone } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Carregando, Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { haQuantoTempo } from "@/features/compras/textos";
import { ApiError } from "@/lib/api";
import { mudarParams } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { AvisosRoteiro } from "./avisos-roteiro";
import { diaCurto, diaEMesBR, maiuscula, nomeDoDia, numeroDoDia } from "./datas";
import { useMarcarPasso, useRoteiro } from "./queries";
import { numeroCurto, ROTULO_TIPO } from "./textos";
import type { Passo, SessaoNoRoteiro } from "./types";

const NO_DIA = "no_dia";

/**
 * Roteiro de preparo (`CardapioPreparoCelular`): uma aba por sessão (a que já
 * passou, apagada), os passos na ordem que a API devolve (pelo que demora
 * mais), a caixa de "feito", porções, destino e avisos. Tela cheia no
 * celular, painel lateral no computador (`#cardapio?roteiro=1`).
 */
export function RoteiroPainel({
  aberto,
  semanaId,
  hoje,
  quem,
  sessaoInicial,
  onNovaSessao,
}: {
  aberto: boolean;
  semanaId: number;
  hoje: string;
  quem: string | null;
  /** A sessão que o endereço pede (`sessao=`), se houver. */
  sessaoInicial: string | null;
  onNovaSessao: () => void;
}) {
  return (
    <Dialogo
      aberto={aberto}
      onFechar={() => mudarParams({ roteiro: null, sessao: null }, { substituir: true })}
      titulo="Roteiro de preparo"
      lateral
      larga
    >
      {aberto ? (
        <Conteudo
          semanaId={semanaId}
          hoje={hoje}
          quem={quem}
          sessaoInicial={sessaoInicial}
          onNovaSessao={onNovaSessao}
        />
      ) : null}
    </Dialogo>
  );
}

function rotuloDaAba(s: SessaoNoRoteiro, hoje: string): { titulo: string; apoio: string } {
  const passou = s.data < hoje;
  return {
    titulo: `${maiuscula(nomeDoDia(s.data))} ${numeroDoDia(s.data)}`,
    apoio: passou ? "já passou" : `${s.passos.length} ${s.passos.length === 1 ? "passo" : "passos"}`,
  };
}

function Conteudo({
  semanaId,
  hoje,
  quem,
  sessaoInicial,
  onNovaSessao,
}: {
  semanaId: number;
  hoje: string;
  quem: string | null;
  sessaoInicial: string | null;
  onNovaSessao: () => void;
}) {
  const roteiro = useRoteiro(semanaId);
  const marcar = useMarcarPasso(quem ?? "");
  const idPainel = useId();
  const [escolhida, setEscolhida] = useState<string | null>(sessaoInicial);
  const [aviso, setAviso] = useState<string | null>(null);

  if (roteiro.isLoading) return <Carregando rotulo="Carregando o roteiro" alturas={["h-26", "h-120"]} />;
  if (roteiro.isError || !roteiro.data) {
    return (
      <Falha
        titulo="Não foi possível ler o roteiro"
        erro={roteiro.error}
        onTentar={() => void roteiro.refetch()}
      />
    );
  }

  const { sessoes, no_dia, avisos } = roteiro.data;
  // Sem escolha: a primeira sessão que ainda não passou; depois, a última.
  const padrao =
    sessoes.find((s) => s.data >= hoje)?.sessao_id ?? sessoes[sessoes.length - 1]?.sessao_id;
  const aba =
    escolhida === NO_DIA || (escolhida && sessoes.some((s) => String(s.sessao_id) === escolhida))
      ? escolhida
      : padrao !== undefined
        ? String(padrao)
        : NO_DIA;
  const sessao = sessoes.find((s) => String(s.sessao_id) === aba);

  function alternar(s: SessaoNoRoteiro, p: Passo) {
    if (!quem) return;
    setAviso(null);
    marcar.mutate(
      { sessaoId: s.sessao_id, receitaId: p.receita.id, feito: !p.feito },
      {
        onError: (e) =>
          setAviso(
            `${p.receita.nome} voltou ao que era: ${
              e instanceof ApiError ? e.detail : "não foi possível falar com o servidor."
            }`,
          ),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="text-apoio text-texto-2 m-0">
        Cada passo é uma receita a fazer na sessão. Marque o que já foi feito: o outro celular vê
        em poucos segundos.
      </p>

      <div className="flex items-start gap-3">
        <Abas
          rotulo="Sessão de preparo"
          fundo="superficie-2"
          idPainel={idPainel}
          atual={aba}
          onMudar={setEscolhida}
          className="flex-1"
          abas={[
            ...sessoes.map((s) => {
              const r = rotuloDaAba(s, hoje);
              return {
                id: String(s.sessao_id),
                rotulo: (
                  <span className={cn("flex flex-col items-start leading-tight", s.data < hoje && "opacity-70")}>
                    <span>{r.titulo}</span>
                    <span className="text-selo">{r.apoio}</span>
                  </span>
                ),
              };
            }),
            {
              id: NO_DIA,
              rotulo: (
                <span className="flex flex-col items-start leading-tight">
                  <span>No dia</span>
                  <span className="text-selo">
                    {no_dia.length} {no_dia.length === 1 ? "prato" : "pratos"}
                  </span>
                </span>
              ),
            },
          ]}
        />
        <BotaoIcone
          rotulo="Adicionar sessão"
          className="bg-superficie-2"
          disabled={!quem}
          onClick={onNovaSessao}
        >
          <Icone nome="adicionar" tamanho={18} espessura={2.4} />
        </BotaoIcone>
      </div>

      <p role="status" className="text-apoio text-texto-2 m-0 empty:hidden">
        {aviso}
      </p>

      <div id={idPainel} role="tabpanel" className="flex flex-col gap-4">
        {aba === NO_DIA ? (
          <section aria-label="No dia" className="flex flex-col">
            <h3 className="text-bloco font-forte m-0 pb-3">Na hora, sem sessão</h3>
            {no_dia.length === 0 ? (
              <p className="text-apoio text-texto-2 m-0">Nenhum prato fica para fazer na hora.</p>
            ) : (
              no_dia.map((n) => (
                <div
                  key={n.refeicao_id}
                  className="linha-acima flex min-h-22 items-center justify-between gap-4 py-3"
                >
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="text-corpo font-semibold">{n.receita.nome}</span>
                    <span className="text-pequeno text-texto-2">
                      {maiuscula(diaCurto(n.dia))} {diaEMesBR(n.dia)} · {ROTULO_TIPO[n.tipo]}
                    </span>
                  </span>
                  {n.receita.tempo_preparo_min ? (
                    <span className="text-apoio text-texto-apoio shrink-0">
                      {n.receita.tempo_preparo_min} min
                    </span>
                  ) : null}
                </div>
              ))
            )}
          </section>
        ) : sessao ? (
          <section aria-label={`Sessão de ${nomeDoDia(sessao.data)}`} className="flex flex-col">
            <div className="flex items-baseline justify-between gap-4 pb-3">
              <h3 className="text-bloco font-forte m-0">Na ordem, pelo que demora mais</h3>
              <span className="text-pequeno text-texto-2 shrink-0">
                {sessao.passos.filter((p) => p.feito).length} de {sessao.passos.length} feitos
              </span>
            </div>
            <p className="text-pequeno text-texto-2 m-0 pb-2">
              {maiuscula(nomeDoDia(sessao.data))}, {diaEMesBR(sessao.data)}
              {sessao.rotulo ? ` · ${sessao.rotulo}` : ""}
              {sessao.data < hoje ? " · já passou" : ""}
            </p>
            {sessao.passos.length === 0 ? (
              <p className="text-apoio text-texto-2 m-0 py-4">
                Nenhuma receita cai nesta sessão. Ela some do roteiro se continuar vazia.
              </p>
            ) : (
              sessao.passos.map((p) => (
                <LinhaPasso
                  key={p.receita.id}
                  passo={p}
                  desabilitado={!quem}
                  onAlternar={() => alternar(sessao, p)}
                />
              ))
            )}
          </section>
        ) : null}
      </div>

      <AvisosRoteiro avisos={avisos} />
    </div>
  );
}

/** "Geladeira até sáb 21/11" ou "2,5 na geladeira" + "2 no congelador · descongelar qui 26/11". */
function destinosDoPasso(p: Passo): { geladeira: string | null; congelador: string | null } {
  const naGeladeira = p.destinos.filter((d) => d.onde === "geladeira");
  const noCongelador = p.destinos.filter((d) => d.onde === "congelador");
  const ate = naGeladeira.reduce((max, d) => (d.dia > max ? d.dia : max), "");
  const descongelar = noCongelador.map((d) => d.descongelar_em).filter((d): d is string => !!d).sort()[0];
  return {
    geladeira:
      naGeladeira.length === 0
        ? null
        : noCongelador.length > 0
          ? `${numeroCurto(p.porcoes_geladeira)} na geladeira`
          : `Geladeira até ${diaCurto(ate)} ${diaEMesBR(ate)}`,
    congelador:
      noCongelador.length === 0
        ? null
        : `${numeroCurto(p.porcoes_congelador)} no congelador${
            descongelar ? ` · descongelar ${diaCurto(descongelar)} ${diaEMesBR(descongelar)}` : ""
          }`,
  };
}

/** Uma linha do roteiro: a caixa de "feito" de 28px num alvo de toque de 56px, como a lista. */
function LinhaPasso({
  passo,
  desabilitado,
  onAlternar,
}: {
  passo: Passo;
  desabilitado: boolean;
  onAlternar: () => void;
}) {
  const feito = passo.feito !== null;
  const { geladeira, congelador } = destinosDoPasso(passo);
  return (
    <label
      className={cn(
        "linha-acima flex min-h-28 cursor-pointer items-start gap-7 px-1 py-4",
        desabilitado && "cursor-not-allowed",
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={feito}
        disabled={desabilitado}
        onChange={onAlternar}
      />
      <span
        aria-hidden
        className={cn(
          "rounded-campo mt-1 flex size-14 shrink-0 items-center justify-center",
          "peer-focus-visible:outline-destaque peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2",
          feito ? "bg-receita text-white" : "bg-superficie shadow-[inset_0_0_0_2px_var(--color-caixa)]",
        )}
      >
        {feito ? <Icone nome="revisar" tamanho={16} espessura={3} /> : null}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="flex items-baseline justify-between gap-4">
          <span className={cn(feito ? "text-texto-2 line-through" : "font-[600]", "text-[17px]")}>
            {passo.receita.nome}
          </span>
          {passo.receita.tempo_preparo_min ? (
            <span className="text-apoio text-texto-apoio shrink-0">
              {passo.receita.tempo_preparo_min} min
            </span>
          ) : null}
        </span>
        <span className="text-pequeno text-texto-2">
          {numeroCurto(passo.porcoes)} {Number(passo.porcoes) === 1 ? "porção" : "porções"}
        </span>
        <span className="flex flex-wrap gap-x-4 gap-y-1">
          {geladeira ? <span className="text-pequeno text-texto-apoio">{geladeira}</span> : null}
          {congelador ? (
            <span className="text-selo bg-destaque-fundo text-destaque-hover rounded-selo px-3 py-px font-semibold">
              {congelador}
            </span>
          ) : null}
        </span>
        {passo.avisos.map((a) => (
          <span key={a} className="text-pequeno text-atencao-texto bg-atencao-fundo-2 rounded-selo px-3 py-2">
            {a}
          </span>
        ))}
        {passo.feito ? (
          <span className="text-selo text-receita-texto">
            Feito por {passo.feito.por} {haQuantoTempo(passo.feito.em)}
          </span>
        ) : null}
      </span>
    </label>
  );
}
