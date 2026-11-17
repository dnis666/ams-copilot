---
id: KB-007
title: Dump TIME_OUT em relatório Z
module: ABAP
transactions: ST22, SE30, ST05, SE38
---

# Dump TIME_OUT em relatório Z

## Sintomas
- Relatório customizado termina com runtime error TIME_OUT na ST22.
- O problema aparece com períodos ou volumes maiores de dados.

## Causa
O programa ultrapassou o tempo máximo de execução em diálogo, normalmente por SELECT sem índice, leitura em loop (SELECT dentro de LOOP) ou tabela interna sem chave.

## Resolução
1. Analisar o dump na ST22 e identificar a instrução e o programa onde o tempo estourou.
2. Medir o programa com ST05 (trace de SQL) e SE30 para achar os acessos mais caros.
3. Corrigir o código: usar FOR ALL ENTRIES ou JOIN, tabela interna SORTED/HASHED e campos indexados no WHERE.
4. Como contorno, orientar a execução em background (SE38 com variante agendada).
5. Transportar a correção após teste em qualidade com volume parecido com o de produção.
