import { Button } from "@/components/ui/controls";

/** Skeleton de carregamento (`shimmerPulse` do protótipo). */
export function TabelaCarregando({ linhas = 8 }: { linhas?: number }) {
  return (
    <div className="p-5" aria-busy aria-label="Carregando transações">
      {Array.from({ length: linhas }, (_, i) => (
        <div key={i} className="px-8 py-5">
          <div
            className="bg-surface animate-shimmer h-7 rounded-md"
            style={{ width: `${60 + ((i * 13) % 35)}%` }}
          />
        </div>
      ))}
    </div>
  );
}

export function TabelaVazia({
  temFiltro,
  onLimparFiltros,
  onNova,
}: {
  temFiltro: boolean;
  onLimparFiltros: () => void;
  onNova: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-5 px-12 py-32 text-center">
      <div className="text-title text-text-primary font-semibold">
        Nenhuma transação encontrada
      </div>
      <p className="text-body text-text-tertiary max-w-180">
        {temFiltro
          ? "Ajuste os filtros ou cadastre a primeira transação do período."
          : "Cadastre a primeira transação para começar."}
      </p>
      <div className="mt-2 flex gap-4">
        {temFiltro ? (
          <Button variant="secondary" onClick={onLimparFiltros}>
            Limpar filtros
          </Button>
        ) : null}
        <Button onClick={onNova}>+ Nova transação</Button>
      </div>
    </div>
  );
}

export function TabelaErro({ mensagem, onTentar }: { mensagem: string; onTentar: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-5 px-12 py-32 text-center"
    >
      <div className="text-title text-expense font-semibold">
        Não foi possível carregar as transações
      </div>
      <p className="text-body text-text-tertiary max-w-180">{mensagem}</p>
      <Button onClick={onTentar}>Tentar novamente</Button>
    </div>
  );
}
