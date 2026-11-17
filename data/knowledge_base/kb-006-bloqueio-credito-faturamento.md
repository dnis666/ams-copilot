---
id: KB-006
title: Remessa ou ordem bloqueada por limite de crédito
module: SD
transactions: VKM3, VKM1, FD32, VF01, VA02
---

# Bloqueio por limite de crédito

## Sintomas
- Ordem de venda ou remessa com status de crédito "bloqueado".
- Não é possível criar a remessa ou o faturamento (VF01) para o cliente.

## Causa
O valor em aberto do cliente ultrapassou o limite de crédito definido na FD32 ou o documento caiu em verificação dinâmica de crédito.

## Resolução
1. Consultar a exposição de crédito do cliente na FD32.
2. Enviar ao responsável de crédito a lista de documentos bloqueados da VKM1.
3. Após aprovação, liberar o documento na VKM3 ou ajustar o limite na FD32.
4. Seguir com remessa e faturamento (VL01N e VF01).
