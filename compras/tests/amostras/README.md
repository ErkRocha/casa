# Amostras de NFC-e para os testes

O leitor `compras/nfce/leitor_svrs.py` foi escrito sem nenhuma nota real
(02/11/2026), seguindo o layout presumido do portal SVRS. O teste
`test_leitor_com_amostra_real_anonimizada` fica **pulado** até existir aqui
o arquivo `nfce_rs_anonimizada.html`.

**O repositório é público.** Nada de nota real sem anonimizar.

## Como fornecer a amostra

1. Pegue uma NFC-e de mercado do RS e leia pelo serviço
   (`POST /api/compras/notas`, ver o README da raiz). A página fica guardada
   inteira em `compras.notas_fiscais.conteudo_original`.
2. Salve a página **fora do git**, com o sufixo `.bruta.html` (o
   `.gitignore` recusa esse sufixo nesta pasta):

   ```bash
   source scripts/local/ambiente.sh && cd compras && python - <<'EOF'
   from sqlalchemy import text
   from compras.db import engine
   with engine.connect() as c:
       dado = c.execute(text(
           "SELECT conteudo_original FROM compras.notas_fiscais "
           "WHERE deleted_em IS NULL ORDER BY id DESC LIMIT 1"
       )).scalar_one()
   open("tests/amostras/nota.bruta.html", "wb").write(dado)
   EOF
   ```

   (ou peça ao Claude Code para extrair a última nota.)
3. Anonimize numa cópia `nfce_rs_anonimizada.html`, mantendo a estrutura
   HTML intacta (tags, `id`, `class`):
   - **CPF do consumidor**, nome e qualquer dado do comprador: apague ou
     troque por `000.000.000-00`;
   - **chave de acesso**, protocolo de autorização e QR code: troque por
     dígitos inventados;
   - forma de pagamento e últimos dígitos de cartão: troque;
   - CNPJ, razão social e endereço do mercado podem ficar (são públicos),
     ou troque se preferir; os itens e valores podem ficar.
4. Rode `cd compras && pytest tests/test_nfce.py`. Se o teste falhar, o
   layout real é outro: ajuste o leitor (com outra `VERSAO`) e acrescente
   asserções específicas da amostra.
