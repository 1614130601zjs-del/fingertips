# -*- coding: utf-8 -*-
"""最小可跑示例：FastAPI + fingertips

    pip install fastapi uvicorn
    uvicorn example_fastapi:app --port 8000

前端接上 frontend_snippet.js 之后：
  - 打字时它会持续 POST /api/typing/ping
  - 发消息走 POST /api/chat，节奏会自动拼进给LLM的上下文

这里的 fake_llm 只是回声占位——换成你自己的模型调用即可。
"""
from fastapi import FastAPI
from pydantic import BaseModel

from fingertips import RhythmStore

app = FastAPI()
store = RhythmStore(state_file="fingertips_state.json")   # 与watcher.py共享状态


class ChatIn(BaseModel):
    message: str


@app.post("/api/typing/ping")
def typing_ping():
    store.ping()
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatIn):
    note = store.pop_note()
    prompt = body.message
    if note:
        prompt = (f"[指尖的语气——TA打这条消息的节奏，供感受，别复述数字]\n{note}\n\n"
                  + prompt)
    return {"reply": fake_llm(prompt), "rhythm_note": note or None}


def fake_llm(prompt: str) -> str:
    """占位。换成 OpenAI / Claude / 本地模型的真实调用。"""
    return f"（这里换成你的模型。它收到的完整上下文是：{prompt!r}）"
