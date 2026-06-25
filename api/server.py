import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from models.db import get_engine, create_session
from services.auth import authenticate
from services.agent_runtime import AgentRuntime
from agents import orchestrator
from api.schemas import ChatCompletionRequest, ChatCompletionResponse, ChatChoice, ChatChoiceMessage

app = FastAPI(title="Naatomatic API", version="1.0.0")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(exist_ok=True)
(_STATIC_DIR / "charts").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

engine = get_engine()

def get_db():
    db = create_session(engine)
    try:
        yield db
    finally:
        db.close()


def get_personal_number(
    x_personal_number: Optional[str] = Header(default=None, alias="X-Personal-Number"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    if x_personal_number:
        return x_personal_number

    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "").strip()

    raise HTTPException(status_code=401, detail="Personal number is required")

@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [
            {
                "id": "my-orchestrator",
                "object": "model",
                "created": 0,
                "owned_by": "local"
            }
        ]
    }

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    personal_number: str = Depends(get_personal_number),
    db: Session = Depends(get_db)
):
    # Verify we have messages
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Authenticate user and get ToolContext
    ctx = authenticate(db, personal_number)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive personal number")

    # Setup Agent Runtime
    runtime = AgentRuntime(ctx=ctx)

    # Run graph
    try:
        final_answer = orchestrator.run(messages=messages, runtime=runtime)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    
    return ChatCompletionResponse(
        id=response_id,
        created=int(time.time()),
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(role="assistant", content=final_answer)
            )
        ]
    )
