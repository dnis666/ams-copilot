---
id: KB-008
title: Registro bloqueado por outro usuário (SM12)
module: BASIS
transactions: SM12, SM04, SM50
---

# Registro bloqueado por outro usuário

## Sintomas
- Mensagem "O objeto está bloqueado pelo usuário XXXX" ao editar pedido, material ou cliente.
- O usuário dono do bloqueio diz que não está com a transação aberta.

## Causa
Sessão encerrada de forma anormal ou processo travado que manteve a entrada de bloqueio na tabela de enqueue.

## Resolução
1. Localizar a entrada na SM12 pelo usuário ou pelo objeto.
2. Confirmar na SM04 e na SM50 se o usuário ainda tem sessão ou processo ativo.
3. Se não houver sessão ativa, eliminar a entrada de bloqueio na SM12 com registro no chamado.
4. Se houver processo travado, encerrar o processo e verificar se o documento ficou consistente.
