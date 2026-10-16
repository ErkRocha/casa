/** Espelho de `app/schemas/revisar.py`. */

export interface MotivoRevisao {
  /** `possivel_duplicata`, `encargos`, `pagamento_fatura_cartao`, `transferencia`... */
  motivo: string;
  rotulo: string;
  quantidade: number;
}

export interface RevisarResumo {
  total: number;
  motivos: MotivoRevisao[];
}
