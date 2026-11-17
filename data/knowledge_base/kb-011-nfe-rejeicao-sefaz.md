---
id: KB-011
title: NF-e rejeitada pela SEFAZ no monitor do GRC
module: FISCAL
transactions: J1BNFE, /XNFE/NFE_MONITOR, J1B3N
---

# NF-e rejeitada pela SEFAZ

## Sintomas
- Nota fiscal eletrônica com status "Rejeitada" no monitor J1BNFE ou no monitor do GRC.
- Faturamento concluído no SD, mas o DANFE não é liberado para o transporte.

## Causa
Dados fiscais inconsistentes no documento (NCM, CFOP, CST, código de benefício, IE do destinatário) ou regra de validação nova publicada em nota técnica da SEFAZ.

## Resolução
1. Ler no monitor o código e o motivo da rejeição retornados pela SEFAZ.
2. Corrigir o dado de origem (material, cliente ou determinação de impostos) conforme o código de rejeição.
3. Cancelar a fatura e o documento fiscal rejeitado e refaturar, ou reenviar se a correção não exigir novo documento.
4. Se a rejeição vier de nota técnica nova, abrir chamado para atualização do pacote fiscal.
