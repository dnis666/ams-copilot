import argparse
import json
import sys
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ams_copilot.config import get_settings
from ams_copilot.evaluation import evaluate, load_cases
from ams_copilot.models import Ticket
from ams_copilot.pipeline import build_container
from ams_copilot.rag import load_documents


def _index(_: argparse.Namespace) -> int:
    settings = get_settings()
    with closing(build_container(settings)) as container:
        total = container.knowledge_base.index(load_documents(settings.knowledge_base_dir))
        print(f"{total} trechos indexados a partir de {settings.knowledge_base_dir}")
        return 0


def _triage(args: argparse.Namespace) -> int:
    with closing(build_container(get_settings())) as container:
        ticket = Ticket(
            id=f"CLI-{uuid4().hex[:8].upper()}",
            tenant=args.tenant,
            title=args.title,
            description=args.description,
        )
        print(container.pipeline.run(ticket).model_dump_json(indent=2))
        return 0


def _evaluate(args: argparse.Namespace) -> int:
    with closing(build_container(get_settings())) as container:
        report = evaluate(container.pipeline, load_cases(Path(args.dataset)))
        summary = {key: value for key, value in asdict(report).items() if key != "failures"}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
        for failure in report.failures:
            print(
                f"falha {failure['case_id']}: módulo {failure['predicted_module']} (esperado {failure['expected_module']}), "
                f"docs {failure['retrieved_docs']} (esperado {failure['expected_doc']})",
                file=sys.stderr,
            )
        problems = report.gates(args.min_module_accuracy, args.min_retrieval_hit_rate)
        for problem in problems:
            print(f"gate reprovado: {problem}", file=sys.stderr)
        return 1 if problems else 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("ams_copilot.api:app", host=args.host, port=args.port)
    return 0


def _mcp(_: argparse.Namespace) -> int:
    from ams_copilot.mcp_server import main as run_mcp

    run_mcp()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ams-copilot")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("index", help="indexa a base de conhecimento").set_defaults(handler=_index)

    triage = commands.add_parser("triage", help="executa a triagem de um chamado")
    triage.add_argument("--tenant", required=True)
    triage.add_argument("--title", required=True)
    triage.add_argument("--description", required=True)
    triage.set_defaults(handler=_triage)

    evaluation = commands.add_parser("eval", help="roda o conjunto de avaliação com gates de qualidade")
    evaluation.add_argument("--dataset", default="evals/dataset.jsonl")
    evaluation.add_argument("--output", default="evals/report.json")
    evaluation.add_argument("--min-module-accuracy", type=float, default=0.8)
    evaluation.add_argument("--min-retrieval-hit-rate", type=float, default=0.8)
    evaluation.set_defaults(handler=_evaluate)

    serve = commands.add_parser("serve", help="sobe a API HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(handler=_serve)

    commands.add_parser("mcp", help="sobe o servidor MCP via stdio").set_defaults(handler=_mcp)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
