---
id: KB-001
title: IDoc de entrada em status 51 (documento de aplicação não lançado)
module: INTEGRATION
transactions: WE02, WE19, BD87, WE20
---

# IDoc de entrada em status 51

## Sintomas
- Pedidos ou notas vindos do sistema externo não aparecem no SAP.
- Na WE02 o IDoc (ORDERS, INVOIC, DESADV) está em status 51 "Documento de aplicação não lançado".
- A mensagem de erro do IDoc cita material, centro, parceiro ou unidade de medida inexistente.

## Causa
Dados mestre ausentes ou divergentes entre o sistema emissor e o SAP (material não ampliado para o centro, parceiro sem cadastro no perfil de parceiro ou unidade de medida sem conversão), o que impede a função de entrada de gerar o documento.

## Resolução
1. Abrir o IDoc na WE02 e ler o registro de status 51 para identificar o campo rejeitado.
2. Corrigir o dado mestre apontado (MM02 para ampliar material, XD02/XK02 para parceiro, WE20 para perfil de parceiro).
3. Reprocessar o IDoc pela BD87 selecionando o status 51.
4. Se o conteúdo do IDoc estiver errado, gerar cópia de teste na WE19, ajustar o segmento e processar, registrando o número do IDoc original no chamado.
5. Confirmar o documento gerado (VA03, MIR4 ou VL03N conforme o tipo de mensagem).
