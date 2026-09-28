/**
 * Client HTTP da API.
 *
 * Sem biblioteca: `fetch` resolve, e o cache/refetch é do TanStack Query. O
 * que mora aqui é montagem de URL, erro tipado e nada mais.
 */

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    /** `detail` do FastAPI — já vem em pt-BR, pronto para a tela. */
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }

  /** 409 = o banco recusou (dedup, unique, check). Merece texto próprio. */
  get isConflito(): boolean {
    return this.status === 409;
  }
}

/** Valor aceito num query string. `undefined` e `null` somem da URL. */
type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();

  for (const [chave, valor] of Object.entries(params)) {
    if (valor === undefined || valor === null || valor === "") continue;

    if (Array.isArray(valor)) {
      // FastAPI lê `?categoria_ids=1&categoria_ids=2` como lista.
      for (const item of valor) search.append(chave, String(item));
    } else {
      search.append(chave, String(valor));
    }
  }

  const texto = search.toString();
  return texto ? `?${texto}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData monta o próprio `Content-Type` com o boundary do multipart.
  // Definir o header à mão aqui quebraria o upload de PDF.
  const ehFormData = init?.body instanceof FormData;

  let resposta: Response;
  try {
    resposta = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(ehFormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch (causa) {
    // API fora do ar, container caído, CORS. Não é erro de status.
    throw new ApiError(0, "Não foi possível falar com a API. Ela está no ar?");
  }

  if (!resposta.ok) {
    throw new ApiError(resposta.status, await extrairDetalhe(resposta));
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

async function extrairDetalhe(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    const detail = corpo?.detail;

    if (typeof detail === "string") return detail;

    // 422 do Pydantic vem como lista de erros por campo.
    if (Array.isArray(detail)) {
      return detail
        .map((erro) => {
          const campo = Array.isArray(erro?.loc) ? erro.loc.slice(1).join(".") : "";
          return campo ? `${campo}: ${erro.msg}` : erro.msg;
        })
        .join("; ");
    }
  } catch {
    // Corpo não era JSON — cai no genérico abaixo.
  }
  return `Erro ${resposta.status} ao chamar a API.`;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  /** Upload de arquivo. O `Content-Type` fica por conta do FormData. */
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** Envelope de listagem paginada da API. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
