#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fingertips MCP Server (Pure FastAPI, no mcp SDK dependency)

兼容 MCP Streamable HTTP 协议，零额外依赖（除了 fastapi/uvicorn）。
"""
import argparse
import asyncio
import json
import os
import time as _time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

# ---------------------------------------------------------------------------
# 1. 内嵌 fingertips 核心
# ---------------------------------------------------------------------------
PING_KEEP = 300
STATE_FILE = os.environ.get("FINGERTIPS_STATE", "fingertips_state.json")


class RhythmStore:
    def __init__(self, orphan_after_sec=600, min_note_sec=20,
                 pause_gap_sec=15, state_file=None):
        self.orphan_after = orphan_after_sec
        self.min_note = min_note_sec
        self.pause_gap = pause_gap_sec
        self.state_file = Path(state_file) if state_file else None
        self.pings = []
        self.orphan = None
        self._load()

    def _load(self):
        if not self.state_file:
            return
        try:
            d = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.pings = d.get("pings", [])
            self.orphan = d.get("orphan")
        except Exception:
            pass

    def _save(self):
        if not self.state_file:
            return
        try:
            self.state_file.write_text(json.dumps(
                {"pings": self.pings, "orphan": self.orphan}), encoding="utf-8")
        except Exception:
            pass

    def _gc(self):
        if self.pings and _time.time() - self.pings[-1] > self.orphan_after:
            if self.pings[-1] - self.pings[0] >= 5:
                self.orphan = {"start": self.pings[0], "end": self.pings[-1]}
            self.pings.clear()

    def ping(self):
        self._load()
        self._gc()
        self.pings.append(_time.time())
        del self.pings[:-PING_KEEP]
        self._save()

    def pop_note(self) -> str:
        self._load()
        self._gc()
        notes = []
        if self.orphan:
            mins = int((_time.time() - self.orphan["end"]) / 60)
            dur = int(self.orphan["end"] - self.orphan["start"])
            notes.append(
                f"TA {mins}分钟前打过{dur}秒的字，那条没有发出来"
                "（打了什么无人知晓，包括系统）"
            )
            self.orphan = None
        if self.pings:
            dur = int(self.pings[-1] - self.pings[0])
            gaps = sum(1 for a, b in zip(self.pings, self.pings[1:])
                       if b - a > self.pause_gap)
            if dur >= self.min_note or gaps:
                seg = f"这条消息TA打了{dur}秒"
                if gaps:
                    seg += f"，中途停下来想了{gaps}次"
                notes.append(seg)
            self.pings.clear()
        self._save()
        return "；".join(notes)

    def peek(self) -> dict:
        self._load()
        self._gc()
        self._save()
        return {
            "typing_now": bool(self.pings and _time.time() - self.pings[-1] < 300),
            "orphan": dict(self.orphan) if self.orphan else None,
        }

    def consume_orphan(self):
        self._load()
        o, self.orphan = self.orphan, None
        self._save()
        return o


store = RhythmStore(state_file=STATE_FILE)

# ---------------------------------------------------------------------------
# 2. MCP Protocol Implementation (Pure FastAPI)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_typing_status",
        "description": "获取用户当前是否在输入框中打字。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_message_rhythm",
        "description": "提取最近一条已发送消息的打字节奏（斟酌痕迹）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_unsent_thoughts",
        "description": "检查用户是否有\"打了又删、未发出\"的内容（欲言又止）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_full_rhythm_context",
        "description": "获取完整的打字节奏上下文，供 AI 感受用户当前情绪状态。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_tool_call(name: str, _args: dict) -> list:
    """执行 tool，返回 MCP content 列表"""
    if name == "get_typing_status":
        status = store.peek()
        text = "TA 此刻正在输入框里打字。" if status["typing_now"] else "TA 此刻没有在打字。"
        return [{"type": "text", "text": text}]

    elif name == "get_message_rhythm":
        note = store.pop_note()
        if not note:
            note = "这条消息没有犹豫痕迹，可能是快问快答。"
        return [{"type": "text", "text": note}]

    elif name == "check_unsent_thoughts":
        status = store.peek()
        orphan = status.get("orphan")
        if not orphan:
            return [{"type": "text", "text": "最近没有检测到欲言又止。"}]
        mins = int((_time.time() - orphan["end"]) / 60)
        dur = int(orphan["end"] - orphan["start"])
        store.consume_orphan()
        return [{"type": "text", "text": f"TA {mins}分钟前打了{dur}秒的字，最后没有发出来。"}]

    elif name == "get_full_rhythm_context":
        parts = []
        status = store.peek()
        if status["typing_now"]:
            parts.append("TA 此刻正在输入框里打字。")
        note = store.pop_note()
        if note:
            parts.append(note)
        orphan = status.get("orphan")
        if orphan:
            mins = int((_time.time() - orphan["end"]) / 60)
            dur = int(orphan["end"] - orphan["start"])
            store.consume_orphan()
            parts.append(f"TA {mins}分钟前打了{dur}秒的字，最后没有发出来。")
        if not parts:
            return [{"type": "text", "text": "当前没有检测到打字节奏信息。"}]
        return [{"type": "text", "text": "\n".join(parts)}]

    return [{"type": "text", "text": f"未知工具: {name}"}]


# ---------------------------------------------------------------------------
# 3. FastAPI App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="fingertips MCP Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP Streamable HTTP endpoint"""
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fingertips", "version": "1.0.0"},
            }
        })

    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })

    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        content = handle_tool_call(name, args)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": content,
                "isError": False,
            }
        })

    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })


@app.get("/mcp")
async def mcp_get():
    """MCP 健康检查 / SSE 兼容"""
    return JSONResponse({"status": "ok", "server": "fingertips-mcp"})


@app.post("/api/typing/ping")
def typing_ping():
    store.ping()
    return {"ok": True}


@app.get("/api/rhythm/status")
def http_rhythm_status():
    return store.peek()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 4. 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
