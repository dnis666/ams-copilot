---
id: KB-010
title: Documento não imprime (spool em erro)
module: BASIS
transactions: SP01, SPAD, SM50
---

# Documento não imprime

## Sintomas
- Nota, etiqueta ou ordem não sai na impressora.
- Na SP01 a ordem de spool está com status de erro ou em espera.

## Causa
Dispositivo de saída configurado com host ou fila errados, impressora fora da rede ou servidor de spool sem processo livre.

## Resolução
1. Consultar a ordem de spool na SP01 e ler o log da solicitação de saída.
2. Validar na SPAD o dispositivo de saída, o método de acesso e a fila no servidor de impressão.
3. Testar a impressora pela rede com o time de infraestrutura.
4. Reenviar a ordem de spool pela SP01 depois da correção.
