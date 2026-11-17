---
id: KB-009
title: Falha de conexão em destino RFC
module: INTEGRATION
transactions: SM59, SM58, SMGW, STRUST
---

# Falha de conexão em destino RFC

## Sintomas
- Teste de conexão do destino na SM59 falha.
- Chamadas tRFC presas na SM58 e interfaces sem envio.

## Causa
Indisponibilidade do sistema de destino, senha expirada do usuário de comunicação, certificado vencido (SNC/HTTPS) ou mudança de host ou porta do destino.

## Resolução
1. Executar o teste de conexão e o teste de autorização do destino na SM59.
2. Verificar se o usuário de comunicação está bloqueado ou com senha expirada.
3. Para destinos HTTPS, conferir a validade dos certificados na STRUST.
4. Corrigir o destino e reprocessar as chamadas pendentes na SM58.
