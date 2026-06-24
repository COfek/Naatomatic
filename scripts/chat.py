"""Entrypoint: wires AgentRuntime + the LangGraph (agents/orchestrator.py) and runs
one REPL loop through it — Router -> Worker -> Tool Executor -> Validator ->
Presenter, exactly as designed in DESIGN.md §2.

Requires OPENAI_API_KEY (and, since we're using OpenRouter, OPENAI_BASE_URL) in the
environment.

Run:
    .venv\\Scripts\\python.exe scripts\\chat.py
"""

from __future__ import annotations



from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.orchestrator import run
from models.db import create_all, create_session, get_engine
from services.agent_runtime import AgentRuntime
from tools.base import ToolContext

def build_runtime() -> AgentRuntime:
    # In-memory DB: today only the read-only general_knowledge domain is wired up,
    # which doesn't touch the DB — this just satisfies ToolContext's contract.
    engine = get_engine(":memory:")
    create_all(engine)
    session = create_session(engine)
    ctx = ToolContext(session=session, actor_personal_number=None, roles=[])
    return AgentRuntime(ctx=ctx)


def main() -> None:
    runtime = build_runtime()
    print("Naatomatic — Router -> Worker -> Tools -> Presenter. Ctrl+C to exit.\n")
    history: list[dict] = []
    while True:
        try:
            message = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)
        if not message:
            continue
        history.append({"role": "user", "content": message})
        answer = run(history, runtime)
        history.append({"role": "assistant", "content": answer})
        print(answer, "\n")


if __name__ == "__main__":
    main()