---
id: KB-003
title: Usuário sem autorização para executar transação
module: SECURITY
transactions: SU53, SU01, PFCG, SUIM
---

# Usuário sem autorização para executar transação

## Sintomas
- Mensagem "Você não tem autorização para a transação" ou "Sem autorização para ...".
- Acesso negado depois de troca de função ou de transporte de perfis.

## Causa
O perfil atribuído ao usuário não contém o objeto de autorização ou o valor de campo exigido pela transação, normalmente por função incompleta ou perfil não gerado após alteração.

## Resolução
1. Pedir ao usuário que execute a SU53 logo após o erro e anexe a tela ao chamado.
2. Identificar o objeto e o valor de campo faltante na SU53.
3. Verificar na SUIM quais funções já concedem o objeto e se o usuário deveria tê-las.
4. Com aprovação do gestor do processo, ajustar a função na PFCG, gerar o perfil e transportar.
5. Pedir ao usuário que encerre a sessão e teste novamente.
