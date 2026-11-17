---
id: KB-002
title: Job em background cancelado na SM37
module: BASIS
transactions: SM37, ST22, SM21, SM36
---

# Job em background cancelado

## Sintomas
- Job agendado aparece como "Cancelado" na SM37.
- Relatórios ou interfaces que dependem do job não foram atualizados.

## Causa
O passo do job terminou com erro: dump ABAP, variante inválida, usuário de execução bloqueado ou sem autorização, ou falta de recursos no servidor de aplicação.

## Resolução
1. Abrir o job na SM37 e consultar o log do job para localizar a mensagem de erro.
2. Se houver dump, analisar na ST22 pelo horário do cancelamento.
3. Verificar se o usuário de execução está ativo e com autorização (SU01, SU53).
4. Conferir a variante usada no passo do job e corrigir parâmetros inválidos.
5. Reagendar o job na SM36 ou repetir o passo e acompanhar até o status "Concluído".
