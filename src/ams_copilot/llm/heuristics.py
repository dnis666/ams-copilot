import re
import unicodedata

MODULE_KEYWORDS: dict[str, list[str]] = {
    "INTEGRATION": [
        "idoc",
        "we02",
        "we19",
        "bd87",
        "rfc",
        "sm59",
        "interface",
        "integracao",
        "pi/po",
        "status 51",
    ],
    "SECURITY": [
        "autorizacao",
        "su53",
        "pfcg",
        "perfil",
        "acesso negado",
        "sem permissao",
        "usuario bloqueado",
        "senha",
    ],
    "BASIS": [
        "sm37",
        "job",
        "spool",
        "sp01",
        "impressora",
        "sm12",
        "lock",
        "bloqueado por",
        "lentidao",
        "sm50",
    ],
    "ABAP": ["dump", "st22", "time_out", "runtime error", "programa z", "relatorio z", "abap"],
    "FI": [
        "ob52",
        "lancamento contabil",
        "fb01",
        "f-28",
        "conta contabil",
        "periodo contabil",
        "contas a pagar",
    ],
    "MM": ["migo", "pedido de compra", "me21n", "mmpv", "entrada de mercadoria", "recebimento de material"],
    "SD": ["vf01", "fatura", "faturamento", "ordem de venda", "va01", "remessa", "vkm3", "limite de credito"],
    "FISCAL": ["nf-e", "nfe", "sefaz", "rejeicao", "grc", "nota fiscal", "j1bnfe", "danfe"],
    "CO": ["centro de custo", "ksb1", "ordem interna", "rateio", "ko88", "ciclo de distribuicao"],
    "PP": ["ordem de producao", "co11n", "mrp", "md04", "lista tecnica", "apontamento"],
}

P1_SIGNALS = [
    "producao parada",
    "parou a operacao",
    "todos os usuarios",
    "nenhum usuario",
    "faturamento parado",
    "nao conseguimos faturar",
    "caminhoes parados",
]
P2_SIGNALS = ["urgente", "fechamento", "impacta clientes", "varios usuarios", "prazo hoje", "multa"]
P4_SIGNALS = ["duvida", "gostaria de saber", "como faco", "orientacao", "treinamento"]
REQUEST_SIGNALS = [
    "solicito",
    "solicitacao",
    "criar usuario",
    "liberar acesso",
    "incluir perfil",
    "novo usuario",
]


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def classify_module(text: str) -> tuple[str, float, dict[str, int]]:
    normalized = normalize(text)
    scores = {
        module: sum(normalized.count(keyword) for keyword in keywords) for module, keywords in MODULE_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner_up = ranked[1][1]
    if best_score == 0:
        return "BASIS", 0.3, scores
    confidence = 0.55 + 0.4 * (best_score - runner_up) / (best_score + runner_up)
    return best, round(min(confidence, 0.95), 2), scores


def classify_priority(text: str) -> str:
    normalized = normalize(text)
    if any(signal in normalized for signal in P1_SIGNALS):
        return "P1"
    if any(signal in normalized for signal in P2_SIGNALS):
        return "P2"
    if any(signal in normalized for signal in P4_SIGNALS):
        return "P4"
    return "P3"


def classify_type(text: str) -> str:
    normalized = normalize(text)
    if any(signal in normalized for signal in REQUEST_SIGNALS):
        return "service_request"
    if any(signal in normalized for signal in P4_SIGNALS):
        return "question"
    return "incident"


def extract_section(markdown: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_list(section: str) -> list[str]:
    items = []
    for line in section.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip()
        if cleaned:
            items.append(cleaned)
    return items
