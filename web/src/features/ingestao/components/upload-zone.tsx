import { useRef, useState } from "react";

import { Button } from "@/components/ui/controls";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useImportarArquivo } from "../queries";

/**
 * Área de upload do PDF.
 *
 * O arquivo é lido pelo `pdfplumber` dentro do container e **não sai da
 * máquina** (D-08) — vale dizer isso na tela, porque é extrato bancário e a
 * pergunta é legítima.
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
    <div>
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
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-4 rounded-md border border-dashed px-12 py-20 text-center",
          arrastando ? "border-accent bg-accent-soft" : "border-border bg-surface-sunken",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => enviar(e.target.files)}
        />

        <div className="text-title text-text-primary font-semibold">
          {importar.isPending ? "Lendo o PDF..." : "Arraste a fatura ou o extrato aqui"}
        </div>
        <p className="text-body text-text-tertiary max-w-220">
          PDF de fatura ou extrato do Nubank. O arquivo é lido localmente, dentro do
          container — nada é enviado para fora da sua máquina.
        </p>
        <Button variant="secondary" disabled={importar.isPending}>
          Escolher arquivo
        </Button>
      </div>

      {erro ? (
        <p role="alert" className="text-body-sm text-expense mt-5">
          {erro.detail}
        </p>
      ) : null}
    </div>
  );
}
