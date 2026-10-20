import { useRef, useState } from "react";

import { Button } from "@/components/ui/controls";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useImportarArquivo } from "../queries";

/**
 * Área de upload do PDF (fatura ou extrato do Nubank).
 *
 * O arquivo é lido pelo `pdfplumber` dentro do container e **não sai da
 * máquina** (D-08) — vale dizer isso na tela, porque é extrato bancário e a
 * pergunta é legítima. Os itens vão para a revisão.
 */
export function UploadZone({ onImportado }: { onImportado: (id: number) => void }) {
  const [arrastando, setArrastando] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const importar = useImportarArquivo();

  function enviar(arquivos: FileList | null) {
    const arquivo = arquivos?.[0];
    if (!arquivo) return;
    importar.mutate(arquivo, { onSuccess: (dados) => onImportado(dados.id) });
  }

  const erro = importar.error instanceof ApiError ? importar.error : null;

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setArrastando(true);
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastando(false);
          enviar(e.dataTransfer.files);
        }}
        className={cn(
          "rounded-sub flex flex-col items-center justify-center gap-4 border-[1.5px] border-dashed px-9 py-12 text-center",
          arrastando ? "border-destaque bg-destaque-fundo" : "border-contorno bg-superficie-2",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => enviar(e.target.files)}
        />
        <span className="text-enfase font-forte">
          {importar.isPending ? "Lendo o PDF..." : "Arraste a fatura ou o extrato aqui"}
        </span>
        <p className="text-apoio text-texto-2 m-0 max-w-[460px]">
          PDF de fatura ou extrato do Nubank. O arquivo é lido aqui mesmo, dentro do container:
          nada sai da sua máquina.
        </p>
        <Button variant="secondary" disabled={importar.isPending} onClick={() => inputRef.current?.click()}>
          Escolher arquivo
        </Button>
      </div>

      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro.detail}
        </p>
      ) : null}
    </div>
  );
}
