---
id: KB-013
title: Ciclo de rateio de centro de custo sem valores
module: CO
transactions: KSU5, KSB1, KSU3, KO88
---

# Ciclo de rateio sem valores

## Sintomas
- Execução do ciclo de rateio na KSU5 termina sem gerar valores.
- Centros de custo receptores sem o débito esperado no fechamento.

## Causa
Segmento do ciclo com fator de rateio zerado, centro de custo emissor sem saldo no período ou grupo de elementos de custo sem os lançamentos do mês.

## Resolução
1. Consultar o saldo dos centros emissores na KSB1 para o período.
2. Revisar o segmento do ciclo na KSU3 e os fatores de rateio.
3. Executar a KSU5 em modo de teste, validar a lista de receptores e executar em modo produtivo.
