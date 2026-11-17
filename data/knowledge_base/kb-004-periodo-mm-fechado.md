---
id: KB-004
title: Período de materiais fechado ao lançar entrada de mercadoria na MIGO
module: MM
transactions: MIGO, MMPV, MMRV, OMSY
---

# Período de materiais fechado na MIGO

## Sintomas
- Erro "Só são possíveis lançamentos nos períodos AAAA/MM e AAAA/MM" na MIGO.
- Entradas de mercadoria e transferências bloqueadas na virada do mês.

## Causa
O período de materiais da empresa não foi aberto para o mês corrente, porque o job de virada (RMMMPERI) não rodou ou a MMPV não foi executada.

## Resolução
1. Consultar na MMRV os períodos atual e anterior permitidos para a empresa.
2. Executar a MMPV para abrir o período corrente na empresa afetada.
3. Agendar o job RMMMPERI para rodar no primeiro dia de cada mês e evitar a recorrência.
4. Pedir ao usuário que repita o lançamento na MIGO.
