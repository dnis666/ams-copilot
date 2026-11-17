---
id: KB-005
title: Período contábil fechado (erro F5 201) ao lançar documento
module: FI
transactions: OB52, FB01, F-28, FB50
---

# Período contábil fechado

## Sintomas
- Mensagem "Período contábil AAAA/MM não está aberto" ao lançar na FB01, FB50, F-28 ou MIRO.
- Lançamentos de outras áreas (faturamento, entrada de mercadoria) falham na integração contábil.

## Causa
A variante de período contábil na OB52 não contém o mês do lançamento para o tipo de conta usado (+, S, K, D, A, M).

## Resolução
1. Confirmar com a contabilidade se o período deve ser aberto.
2. Ajustar a variante de período na OB52 para o tipo de conta e intervalo de contas afetados.
3. Repetir o lançamento ou reprocessar a interface que falhou.
4. Registrar no chamado a autorização da contabilidade para a alteração.
