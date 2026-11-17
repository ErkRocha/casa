import { Button } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Icone } from "@/components/ui/icone";
import { mudarParams } from "@/lib/rotas";
import { BuscaReceitas } from "./busca-receitas";

/**
 * "Receitas": a busca de todas as receitas, para abrir uma ou criar a nova.
 * Painel lateral no computador, tela cheia no celular (`#cardapio?receitas=1`).
 */
export function ReceitasPainel({ aberto, quem }: { aberto: boolean; quem: string | null }) {
  return (
    <Dialogo
      aberto={aberto}
      onFechar={() => mudarParams({ receitas: null }, { substituir: true })}
      titulo="Receitas"
      lateral
    >
      {aberto ? (
        <div className="flex flex-col gap-6">
          <Button
            disabled={!quem}
            onClick={() => mudarParams({ receitas: null, receita: "nova" }, { substituir: true })}
          >
            <Icone nome="adicionar" tamanho={16} espessura={2.4} />
            Nova receita
          </Button>
          <BuscaReceitas
            onEscolher={(r) =>
              mudarParams({ receitas: null, receita: String(r.id) }, { substituir: true })
            }
          />
        </div>
      ) : null}
    </Dialogo>
  );
}
