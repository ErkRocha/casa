import { BotaoIcone, SelectSobreposto } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { useGruposDeCategoria, usePessoas } from "@/features/cadastros/queries";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import type { BaldePessoa } from "@/features/filters/types";

/**
 * Barra de ação em lote (`LancamentosDesktop`): escura, flutuando no pé da
 * tela enquanto há seleção. "Definir categoria" e "Definir pessoa" aplicam
 * na hora em que se escolhe; a categoria em lote também vira regra (D-09).
 *
 * A exclusão em lote, que a tela anterior tinha, continua aqui, atrás de uma
 * confirmação: é soft delete e volta pela auditoria (D-06).
 */
export function BatchBar({
  quantidade,
  onAplicar,
  onExcluir,
  onCancelar,
  ocupado,
}: {
  quantidade: number;
  onAplicar: (patch: { categoriaId: number | null; pessoa: BaldePessoa | null }) => void;
  onExcluir: () => void;
  onCancelar: () => void;
  ocupado: boolean;
}) {
  const { data: grupos } = useGruposDeCategoria();
  const { data: pessoas = [] } = usePessoas();
  const escolha = "text-apoio rounded-botao bg-escuro-botao min-h-22 px-7 font-semibold text-white";

  return (
    <div
      role="region"
      aria-label="Ações em lote"
      className="bg-escuro rounded-cartao shadow-flutuante fixed bottom-12 left-1/2 z-30 hidden -translate-x-1/2 items-center gap-5 py-5 pr-5 pl-9 text-white md:ml-19 md:flex lg:ml-62"
    >
      <span className="text-corpo pr-3 font-semibold whitespace-nowrap" aria-live="polite">
        {quantidade} selecionado{quantidade > 1 ? "s" : ""}
      </span>

      <SelectSobreposto
        rotulo="Definir categoria dos selecionados"
        mostrar="Definir categoria"
        value=""
        disabled={ocupado}
        onChange={(e) => {
          if (e.target.value) onAplicar({ categoriaId: Number(e.target.value), pessoa: null });
        }}
        className={escolha}
      >
        <option value="" disabled>
          Definir categoria
        </option>
        {grupos.map((grupo) => (
          <optgroup key={grupo.raizId} label={grupo.raizNome}>
            {grupo.opcoes.map((opcao) => (
              <option key={opcao.id} value={opcao.id}>
                {opcao.nome}
              </option>
            ))}
          </optgroup>
        ))}
      </SelectSobreposto>

      <SelectSobreposto
        rotulo="Definir pessoa dos selecionados"
        mostrar="Definir pessoa"
        value=""
        disabled={ocupado}
        onChange={(e) => {
          const valor = e.target.value;
          if (!valor) return;
          // "conjunto" limpa o dono: é NULL no banco, não uma pessoa (D-03).
          onAplicar({
            categoriaId: null,
            pessoa: valor === "conjunto" ? "conjunto" : Number(valor),
          });
        }}
        className={escolha}
      >
        <option value="" disabled>
          Definir pessoa
        </option>
        {pessoas.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
        <option value="conjunto">{ROTULO_JUNTOS}</option>
      </SelectSobreposto>

      <BotaoIcone
        rotulo="Excluir os selecionados"
        disabled={ocupado}
        onClick={() => {
          if (window.confirm(`Excluir ${quantidade} lançamento${quantidade > 1 ? "s" : ""}?`)) {
            onExcluir();
          }
        }}
        className="text-escuro-texto-2 bg-transparent hover:text-white"
      >
        <Icone nome="lixeira" tamanho={16} />
      </BotaoIcone>
      <BotaoIcone
        rotulo="Limpar seleção"
        onClick={onCancelar}
        className="text-escuro-texto-2 bg-transparent hover:text-white"
      >
        <Icone nome="fechar" tamanho={16} espessura={2.2} />
      </BotaoIcone>
    </div>
  );
}
