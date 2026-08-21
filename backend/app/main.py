from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph import ping_graph

app = FastAPI(title="AgentReady API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PingRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ping")
def ping(req: PingRequest):
    result = ping_graph.invoke({"message": req.message, "reply": ""})
    return {"reply": result["reply"]}
