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
 * Os elementos permitidos ganham as classes do design (sem plugin de
 * tipografia): o resto do painel usa os mesmos tokens.
 */

const PROIBIDOS = ["img", "a", "iframe", "script", "style"];

const componentes: Components = {
  h1: ({ children }) => (
    <h3 className="text-title-lg text-text-primary mb-5 font-semibold">{children}</h3>
  ),
  h2: ({ children }) => (
    <h4 className="text-caption text-text-tertiary tracking-caps-wide mt-9 mb-4 font-semibold uppercase">
      {children}
    </h4>
  ),
  h3: ({ children }) => (
    <h5 className="text-body text-text-primary mt-7 mb-3 font-semibold">{children}</h5>
  ),
  p: ({ children }) => <p className="text-body text-text-secondary mb-5 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="text-body text-text-secondary mb-5 list-disc pl-8">{children}</ul>,
  ol: ({ children }) => (
    <ol className="text-body text-text-secondary mb-5 list-decimal pl-8">{children}</ol>
  ),
  li: ({ children }) => <li className="mb-2 leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="text-text-primary font-semibold">{children}</strong>,
  em: ({ children }) => <em className="text-text-tertiary">{children}</em>,
  hr: () => <hr className="border-border-faint my-7" />,
  code: ({ children }) => (
    <code className="bg-surface text-body-sm rounded-sm px-2 font-mono">{children}</code>
  ),
  table: ({ children }) => (
    <table className="text-body-sm text-text-secondary mb-5 w-full border-collapse">{children}</table>
  ),
  th: ({ children }) => (
    <th className="border-border-faint text-text-tertiary border-b py-2 pr-4 text-left">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-border-faint tabular border-b py-2 pr-4">{children}</td>
  ),
};

export function MarkdownSeguro({ texto }: { texto: string }) {
  return (
    <div>
      <Markdown
        skipHtml
        disallowedElements={PROIBIDOS}
        unwrapDisallowed
        components={componentes}
      >
        {texto}
      </Markdown>
    </div>
  );
}
