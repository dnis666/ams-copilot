---
id: KB-012
title: Erro ao apontar ordem de produção na CO11N
module: PP
transactions: CO11N, CO03, COGI, MD04
---

# Erro ao apontar ordem de produção

## Sintomas
- Confirmação na CO11N gera erro de movimento de mercadoria.
- Entradas pendentes acumulando na COGI.

## Causa
Baixa automática de componentes (backflush) sem saldo no depósito, lote obrigatório não informado ou período de materiais fechado.

## Resolução
1. Consultar a COGI e ler o erro de cada movimento pendente.
2. Verificar saldo e lote dos componentes no depósito de consumo.
3. Corrigir o saldo ou o lote e reprocessar os itens na COGI.
4. Confirmar na CO03 que a ordem ficou com os consumos e a entrada corretos.
