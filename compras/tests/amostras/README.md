# Amostras de NFC-e para os testes

**O repositório é público.** Nada de nota real sem anonimizar, e a página
bruta nunca vai para o git.

## O que há aqui

`nfce_rs_anonimizada.html` é a página "Consulta Completa da NFC-e" de uma
nota real (Zaffari, 15/11/2026), anonimizada: CPF zerado; chave, número,
série e protocolo inventados. Itens, valores, CNPJ e endereço do mercado
foram mantidos (são públicos). Lida por `compras/nfce/leitor_completa.py`
(`test_leitor_com_amostra_real_anonimizada`, em `test_nfce.py`). A página
vem em iso-8859-1.

`nfce_rs_anonimizada_out.html` é outra Consulta Completa do mesmo mercado
(Zaffari, 17/10/2026, 7 itens, R$ 323,03), anonimizada do mesmo jeito. O
suco "SUCO NATURALE LARANJA INT 3L" tem o mesmo código interno nas duas
notas; `test_notas_reais.py` usa as duas para provar que a variante
aprendida na primeira reconhece o item na segunda.

`nfce_rs_qrcode_anonimizada.html` é a página do QR code (portal SVRS,
`#tabResult`) de uma nota real (Boa Vista, 19/11/2026, 1 item, R$ 16,99),
lida por `compras/nfce/leitor_svrs.py`. Anonimizada: chave, número, série e
protocolo inventados (a chave inventada mantém UF, mês, CNPJ e modelo e tem
dígito verificador válido); forma de pagamento trocada. A página não traz
CPF ("Consumidor não identificado") nem o hash do QR. Vem em UTF-8. Testada
em `test_nfce.py` (leitor) e `test_notas.py` (leitura pelo link do portal,
sem cair para a chave).

## Como acrescentar uma amostra

1. Leia uma NFC-e de mercado do RS pelo serviço
   (`POST /api/compras/notas`, ver o README da raiz). A página fica guardada
   inteira em `compras.notas_fiscais.conteudo_original`.
2. Salve a página **fora do git**, com o sufixo `.bruta.html` (o
   `.gitignore` recusa esse sufixo nesta pasta). Nunca commite a página
   bruta:

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
3. Anonimize numa cópia, mantendo a estrutura HTML intacta (tags, `id`,
   `class`) e a codificação original (iso-8859-1 na Consulta Completa):
   - **CPF do consumidor**, nome e qualquer dado do comprador: apague ou
     troque por `000.000.000-00`;
   - **chave de acesso**, número, série, protocolo de autorização e QR
     code: troque por dígitos inventados;
   - forma de pagamento e últimos dígitos de cartão: troque;
   - CNPJ, razão social e endereço do mercado podem ficar (são públicos),
     ou troque se preferir; os itens e valores podem ficar.
4. Rode `make compras-test`. Se o teste falhar, o layout mudou: ajuste o
   leitor (com outra `VERSAO`) e acrescente asserções específicas da
   amostra.
