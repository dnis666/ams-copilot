from ams_copilot.agents.base import Agent
from ams_copilot.models import Diagnosis, KbArticle, Review, TriageDecision


class TriageAgent(Agent[TriageDecision]):
    name = "triage_agent"
    task = "triage"
    output_model = TriageDecision
    instructions = (
        "Você é o analista de triagem de um time de AMS SAP. Classifique o chamado pelo módulo SAP responsável, "
        "pela prioridade e pelo tipo. Use P1 só quando a operação do cliente estiver parada para muitos usuários, "
        "P2 para impacto relevante com prazo, P3 para incidentes pontuais e P4 para dúvidas. "
        "Informe uma confiança entre 0 e 1 que reflita a ambiguidade do texto e justifique em uma frase."
    )


class DiagnosisAgent(Agent[Diagnosis]):
    name = "diagnosis_agent"
    task = "diagnosis"
    output_model = Diagnosis
    instructions = (
        "Você é o especialista de diagnóstico de AMS SAP. Antes de responder, consulte a base de conhecimento com "
        "search_knowledge_base e o histórico do cliente com find_similar_tickets. Baseie a causa provável e os "
        "passos de resolução apenas no que as ferramentas retornarem e cite em citations os doc_id usados. "
        "Se nada relevante for encontrado, diga isso, deixe citations vazio e use confiança baixa. "
        "Nunca recomende alteração direta de tabelas em produção."
    )


class ReviewerAgent(Agent[Review]):
    name = "reviewer_agent"
    task = "review"
    output_model = Review
    instructions = (
        "Você revisa diagnósticos antes que cheguem ao analista. Reprove se o diagnóstico citar documentos que não "
        "estão em sources, se os passos não decorrerem das fontes, se houver ação arriscada em produção ou se a "
        "confiança declarada não for compatível com as evidências. Liste cada problema em issues."
    )


class DocumentationAgent(Agent[KbArticle]):
    name = "documentation_agent"
    task = "kb_article"
    output_model = KbArticle
    instructions = (
        "Você transforma um chamado resolvido em artigo da base de conhecimento. Escreva sintomas observáveis, "
        "a causa raiz e os passos de resolução numerados, com as transações SAP envolvidas. Não invente passos "
        "que não estejam nas notas de resolução."
    )
