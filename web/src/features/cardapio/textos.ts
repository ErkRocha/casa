import { numeroCurto } from "@/features/compras/textos";
import { diaEMesBR, noDia } from "./datas";
import type { Refeicao, Roteiro, TipoRefeicao, UnidadeMedida } from "./types";

export { numeroCurto };

export const TIPOS: TipoRefeicao[] = ["cafe_da_manha", "lanche", "almoco", "janta"];

export const ROTULO_TIPO: Record<TipoRefeicao, string> = {
  cafe_da_manha: "Café da manhã",
  lanche: "Lanche",
  almoco: "Almoço",
  janta: "Janta",
};

/** Na ordem em que a cozinha as usa mais. */
export const UNIDADES: Array<{ id: UnidadeMedida; rotulo: string }> = [
  { id: "g", rotulo: "g" },
  { id: "kg", rotulo: "kg" },
  { id: "ml", rotulo: "ml" },
  { id: "l", rotulo: "L" },
  { id: "un", rotulo: "unidade" },
  { id: "colher_sopa", rotulo: "colher de sopa" },
  { id: "colher_cha", rotulo: "colher de chá" },
  { id: "xicara", rotulo: "xícara" },
  { id: "a_gosto", rotulo: "a gosto" },
];

/** O nome do que se come: a receita, ou a observação quando a refeição não tem receita. */
export function nomeDoPrato(refeicao: Refeicao): string {
  if (refeicao.receita) {
    return refeicao.receita.apagada ? `${refeicao.receita.nome} (receita apagada)` : refeicao.receita.nome;
  }
  return refeicao.observacao?.trim() || "Sem prato";
}

/** "150 g", "1,5 colher de sopa", "2 colheres de sopa", "a gosto". */
export function quantidadeDoIngrediente(quantidade: string | null, unidade: UnidadeMedida): string {
  if (unidade === "a_gosto" || quantidade === null) return "a gosto";
  const n = numeroCurto(quantidade);
  const plural = Number(quantidade) > 1;
  switch (unidade) {
    case "un":
      return `${n} un`;
    case "l":
      return `${n} L`;
    case "colher_sopa":
      return `${n} ${plural ? "colheres" : "colher"} de sopa`;
    case "colher_cha":
      return `${n} ${plural ? "colheres" : "colher"} de chá`;
    case "xicara":
      return `${n} ${plural ? "xícaras" : "xícara"}`;
    default:
      return `${n} ${unidade}`;
  }
}

/**
 * Um decimal digitado ("1,5", "0.25", "2") como a API espera ("1.5"), ou
 * nulo. Até três casas, como as quantidades; tudo em texto, sem `float`.
 */
export function decimalDigitado(texto: string): string | null {
  const limpo = texto.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,3})?$/.test(limpo)) return null;
  return limpo.replace(/^0+(?=\d)/, "");
}

/** Um número do formulário de volta para o campo, com vírgula. */
export function decimalParaCampo(valor: string | null): string {
  if (valor === null) return "";
  return numeroCurto(valor);
}

/** Como a refeição fica pronta, vista do roteiro (CardapioSemanaCelular). */
export interface Preparo {
  texto: string;
  /** O roteiro avisa algo dessa refeição: aparece em âmbar. */
  aviso: boolean;
}

/**
 * Para cada refeição, o que o roteiro diz: onde e quando fica pronta ("Pronto
 * no domingo"), se está no congelador ("Congelado: descongelar dia 26/11"),
 * ou "Na hora" quando não vai a nenhuma sessão. Só lê o roteiro, não calcula.
 */
export function preparoPorRefeicao(roteiro: Roteiro | undefined): Map<number, Preparo> {
  const mapa = new Map<number, Preparo>();
  if (!roteiro) return mapa;
  for (const sessao of roteiro.sessoes) {
    for (const passo of sessao.passos) {
      for (const d of passo.destinos) {
        mapa.set(d.refeicao_id, {
          texto:
            d.onde === "congelador"
              ? `Congelado: descongelar${d.descongelar_em ? ` dia ${diaEMesBR(d.descongelar_em)}` : ""}`
              : `Pronto ${noDia(sessao.data)}`,
          aviso: false,
        });
      }
    }
  }
  for (const n of roteiro.no_dia) {
    const min = n.receita.tempo_preparo_min;
    mapa.set(n.refeicao_id, { texto: min ? `Na hora, ${min} min` : "Na hora", aviso: false });
  }
  for (const a of roteiro.avisos) {
    mapa.set(a.refeicao_id, { texto: "Sem preparo: veja o aviso", aviso: true });
  }
  return mapa;
}

/** As cores de "Erik 1,5" e "Laura 1": por ordem de cadastro, a primeira mais escura. */
const TONS_PESSOA = [
  "bg-[#E4EAF8] text-[#1E3A8A]",
  "bg-[#EEF3FD] text-[#2F56B0]",
  "bg-superficie-2 text-texto-apoio",
];

export function tomDaPessoa(indice: number): string {
  return TONS_PESSOA[Math.min(Math.max(indice, 0), TONS_PESSOA.length - 1)] ?? "";
}
