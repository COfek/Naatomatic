import time
import uuid
from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from models.db import get_engine, create_session
from services.auth import authenticate
from services.agent_runtime import AgentRuntime
from agents import orchestrator
from api.schemas import ChatCompletionRequest, ChatCompletionResponse, ChatChoice, ChatChoiceMessage

app = FastAPI(title="Naatomatic API", version="1.0.0")

engine = get_engine()

def get_db():
    db = create_session(engine)
    try:
        yield db
    finally:
        db.close()

def get_personal_number(x_personal_number: str = Header(None, alias="X-Personal-Number")) -> str:
    if not x_personal_number:
        raise HTTPException(status_code=401, detail="X-Personal-Number header is required")
    return x_personal_number

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    personal_number: str = Depends(get_personal_number),
    db: Session = Depends(get_db)
):
    # Verify we have messages
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty")
        
    latest_msg = request.messages[-1].content
    
    # Authenticate user and get ToolContext
    ctx = authenticate(db, personal_number)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive personal number")
        
    # Setup Agent Runtime
    runtime = AgentRuntime(ctx=ctx)
    
    # Run graph
    try:
        # Pass thread_id downstream if orchestrator eventually expects it
        final_answer = orchestrator.run(user_message=latest_msg, runtime=runtime)
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
