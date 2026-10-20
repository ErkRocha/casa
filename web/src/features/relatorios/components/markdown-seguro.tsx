import Markdown, { type Components } from "react-markdown";

/**
 * Markdown de origem NÃO confiável: o texto do relatório vem de um modelo.
 *
 * - Sem HTML bruto: o react-markdown não interpreta HTML (não há rehype-raw),
 *   e `skipHtml` descarta qualquer tag em vez de mostrá-la. Nada de
 *   `dangerouslySetInnerHTML` em lugar nenhum.
 * - Sem imagem e sem link: uma imagem faria o navegador buscar uma URL que o
 *   modelo escolheu (o sistema não vai à internet), e um link levaria para
 *   fora. Os dois saem; o texto do link fica.
 *
 * Os elementos permitidos ganham o visual das pranchetas (`RelatoriosDesktop`):
 * seções em 18px/650, texto em 16px com entrelinha 1,6. O título do mês já
 * está no cabeçalho do artigo: o `#` do texto, que o repete, não aparece.
 */

const PROIBIDOS = ["img", "a", "iframe", "script", "style"];

const SECAO = "text-bloco-celular md:text-bloco font-forte m-0 mt-2 first:mt-0";

const componentes: Components = {
  h1: () => null,
  h2: ({ children }) => <h3 className={SECAO}>{children}</h3>,
  h3: ({ children }) => <h4 className="text-enfase font-forte m-0 mt-1">{children}</h4>,
  p: ({ children }) => <p className="m-0 text-pretty">{children}</p>,
  ul: ({ children }) => <ul className="m-0 flex list-disc flex-col gap-2 pl-9">{children}</ul>,
  ol: ({ children }) => <ol className="m-0 flex list-decimal flex-col gap-2 pl-9">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-forte">{children}</strong>,
  em: ({ children }) => <em className="text-texto-2">{children}</em>,
  hr: () => <hr className="border-linha-suave my-2 w-full border-t" />,
  code: ({ children }) => (
    <code className="bg-superficie-2 text-apoio rounded-campo px-2 py-0.5">{children}</code>
  ),
  table: ({ children }) => (
    <table className="text-apoio w-full border-collapse">{children}</table>
  ),
  th: ({ children }) => (
    <th className="linha-abaixo text-texto-2 py-3 pr-6 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="linha-abaixo-suave py-3 pr-6">{children}</td>,
};

export function MarkdownSeguro({ texto }: { texto: string }) {
  return (
    <div className="text-enfase flex max-w-[640px] flex-col gap-7 leading-[1.6]">
      <Markdown skipHtml disallowedElements={PROIBIDOS} unwrapDisallowed components={componentes}>
        {texto}
      </Markdown>
    </div>
  );
}
