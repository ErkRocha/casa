import { Input } from "@/components/ui/controls";
import { cn } from "@/lib/utils";
import {
  FALTA_LABEL,
  STATUS_ITEM_LABEL,
  type ContagensRevisao,
  type FaltaItem,
  type FiltroRevisao,
  type StatusItem,
} from "../types";

/**
 * Filtros da revisão: situação, o que falta aos pendentes e busca no texto.
 *
 * Existe porque uma sync da Pluggy traz centenas de linhas, e quase todas já
 * foram resolvidas sozinhas (D-21, D-22). O que pede decisão — sem categoria,
 * com observação — tem que estar a um clique. Os números vêm da API e
 * respeitam o período escolhido, e só ele: não mudam com a situação aberta.
 */

const STATUS: StatusItem[] = ["pendente", "aprovado", "rejeitado", "duplicado"];

/** `AAAA-MM-DD` no fuso do navegador (não em UTC, que vira o dia às 21h). */
function iso(d: Date): string {
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
}

function mes(deslocamento: number): { inicio: string; fim: string } {
  const hoje = new Date();
  const inicio = new Date(hoje.getFullYear(), hoje.getMonth() + deslocamento, 1);
  const fim = new Date(hoje.getFullYear(), hoje.getMonth() + deslocamento + 1, 0);
  return { inicio: iso(inicio), fim: iso(fim) };
}

/** Atalhos: os dois períodos que mais se revisam. */
const MESES_RAPIDOS = [
  { rotulo: "Este mês", ...mes(0) },
  { rotulo: "Mês passado", ...mes(-1) },
];
const FALTAS: FaltaItem[] = ["sem_categoria", "observacao", "transferencia", "pronto"];

export function RevisaoFiltros({
  filtro,
  busca,
  contagens,
  onFiltro,
  onBusca,
}: {
  filtro: FiltroRevisao;
  /** O texto digitado, antes do atraso que segura a busca na API. */
  busca: string;
  contagens: ContagensRevisao;
  onFiltro: (filtro: FiltroRevisao) => void;
  onBusca: (texto: string) => void;
}) {
  const total = STATUS.reduce((soma, s) => soma + (contagens.por_status[s] ?? 0), 0);

  return (
    <div className="border-border-faint flex flex-col gap-4 border-b px-8 py-5">
      <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Situação">
        {STATUS.map((status) => {
          const n = contagens.por_status[status] ?? 0;
          if (n === 0 && filtro.status !== status) return null;
          return (
            <Chip
              key={status}
              ativo={filtro.status === status}
              onClick={() => onFiltro({ ...filtro, status, falta: null })}
              rotulo={STATUS_ITEM_LABEL[status]}
              n={n}
            />
          );
        })}
        <Chip
          ativo={filtro.status === null}
          onClick={() => onFiltro({ ...filtro, status: null, falta: null })}
          rotulo="Todos"
          n={total}
        />

        <Input
          type="search"
          value={busca}
          onChange={(e) => onBusca(e.target.value)}
          placeholder="Buscar na linha original"
          aria-label="Buscar na linha original"
          maxLength={100}
          className="text-body-sm ml-auto w-90 py-2.5"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Período">
        <span className="text-caption text-text-tertiary tracking-caps-wide mr-1 font-semibold uppercase">
          Data
        </span>
        <label className="text-body-sm text-text-secondary inline-flex items-center gap-2">
          de
          <Input
            type="date"
            value={filtro.dataDe}
            max={filtro.dataAte || undefined}
            onChange={(e) => onFiltro({ ...filtro, dataDe: e.target.value })}
            className="text-body-sm py-2"
          />
        </label>
        <label className="text-body-sm text-text-secondary inline-flex items-center gap-2">
          até
          <Input
            type="date"
            value={filtro.dataAte}
            min={filtro.dataDe || undefined}
            onChange={(e) => onFiltro({ ...filtro, dataAte: e.target.value })}
            className="text-body-sm py-2"
          />
        </label>
        {MESES_RAPIDOS.map(({ rotulo, inicio, fim }) => (
          <Chip
            key={rotulo}
            ativo={filtro.dataDe === inicio && filtro.dataAte === fim}
            onClick={() => onFiltro({ ...filtro, dataDe: inicio, dataAte: fim })}
            rotulo={rotulo}
          />
        ))}
        {filtro.dataDe || filtro.dataAte ? (
          <button
            type="button"
            onClick={() => onFiltro({ ...filtro, dataDe: "", dataAte: "" })}
            className="text-body-sm text-accent cursor-pointer underline underline-offset-2"
          >
            Limpar datas
          </button>
        ) : null}
      </div>

      {filtro.status === "pendente" ? (
        <div className="flex flex-wrap items-center gap-3" role="group" aria-label="O que falta">
          <span className="text-caption text-text-tertiary tracking-caps-wide mr-1 font-semibold uppercase">
            Falta
          </span>
          <Chip
            ativo={filtro.falta === null}
            onClick={() => onFiltro({ ...filtro, falta: null })}
            rotulo="Todos os pendentes"
            n={contagens.por_status.pendente ?? 0}
          />
          {FALTAS.map((falta) => (
            <Chip
              key={falta}
              ativo={filtro.falta === falta}
              onClick={() => onFiltro({ ...filtro, falta: filtro.falta === falta ? null : falta })}
              rotulo={FALTA_LABEL[falta]}
              n={contagens.pendentes_por_falta[falta] ?? 0}
              destaque={falta === "pronto"}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Chip({
  ativo,
  onClick,
  rotulo,
  n,
  destaque = false,
}: {
  ativo: boolean;
  onClick: () => void;
  rotulo: string;
  /** Sem número, o chip é só um atalho (como "Este mês"). */
  n?: number;
  /** "Prontos para aprovar" com itens: a fila que se resolve em um clique. */
  destaque?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={cn(
        "text-caption-lg inline-flex cursor-pointer items-center gap-2 rounded-md px-4 py-2 font-medium",
        "focus-visible:ring-accent outline-none focus-visible:ring-1",
        ativo
          ? "bg-text-primary text-surface"
          : destaque && (n ?? 0) > 0
            ? "bg-income-soft text-income hover:bg-surface"
            : "bg-surface-sunken text-text-secondary hover:bg-surface",
      )}
    >
      {rotulo}
      {n !== undefined ? (
        <span className={cn("tabular", ativo ? "opacity-80" : "text-text-tertiary")}>{n}</span>
      ) : null}
    </button>
  );
}
