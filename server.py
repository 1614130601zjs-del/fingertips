#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fingertips MCP Server

把 fingertips 包装成 MCP 服务器，支持三种运行模式：
  1. stdio         —— 本地 MCP 客户端（Claude Desktop / Cursor）
  2. http          —— 远程部署（Render / VPS），前端通过 /api/typing/ping 上报
  3. both          —— Termux 本机同时跑 stdio + HTTP（双进程共享状态文件）

铁律：只记节奏，永不记内容。
"""
import argparse
import asyncio
import contextlib
import json
import multiprocessing
import os
import sys
import time as _time
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. 全局配置
# ---------------------------------------------------------------------------
STATE_FILE = os.environ.get("FINGERTIPS_STATE", "fingertips_state.json")

# ---------------------------------------------------------------------------
# 1. 内嵌 fingertips 核心（零外部依赖，MIT 协议）
# ---------------------------------------------------------------------------
PING_KEEP = 300


class RhythmStore:
    """打字节奏账本 —— 只记节奏，永不记内容"""

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


# ---------------------------------------------------------------------------
# 2. MCP Server 定义
# ---------------------------------------------------------------------------
from mcp.server import MCPServer

store = RhythmStore(state_file=STATE_FILE)
mcp = MCPServer("fingertips")


@mcp.tool()
def get_typing_status() -> str:
    """获取用户当前是否在输入框中打字。"""
    status = store.peek()
    if status["typing_now"]:
        return "TA 此刻正在输入框里打字。"
    return "TA 此刻没有在打字。"


@mcp.tool()
def get_message_rhythm() -> str:
    """提取最近一条已发送消息的打字节奏（斟酌痕迹）。

    返回如："这条消息TA打了47秒，中途停下来想了2次"
    或表示没有值得注意的犹豫痕迹。
    """
    note = store.pop_note()
    if not note:
        return "这条消息没有犹豫痕迹，可能是快问快答。"
    return note


@mcp.tool()
def check_unsent_thoughts() -> str:
    """检查用户是否有"打了又删、未发出"的内容（欲言又止）。

    返回如："TA 10分钟前打过40秒的字，那条没有发出来"
    或表示最近没有欲言又止。
    """
    status = store.peek()
    orphan = status.get("orphan")
    if not orphan:
        return "最近没有检测到欲言又止。"
    mins = int((_time.time() - orphan["end"]) / 60)
    dur = int(orphan["end"] - orphan["start"])
    store.consume_orphan()
    return f"TA {mins}分钟前打了{dur}秒的字，最后没有发出来。"


@mcp.tool()
def get_full_rhythm_context() -> str:
    """获取完整的打字节奏上下文，供 AI 感受用户当前情绪状态。

    同时检查：正在打字？已发消息的节奏？欲言又止？
    返回一段自然语言描述，可直接拼进 LLM 提示词。
    """
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
        return "当前没有检测到打字节奏信息。"

    return "\n".join(parts)


@mcp.resource("rhythm://status")
def rhythm_status() -> str:
    """当前打字节奏的原始 JSON 状态。"""
    return json.dumps(store.peek(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 3. HTTP App 工厂（FastAPI + MCP 挂载）
# ---------------------------------------------------------------------------
def create_http_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    mcp_asgi = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with contextlib.AsyncExitStack() as stack:
            if hasattr(mcp, "session_manager"):
                await stack.enter_async_context(mcp.session_manager.run())
            yield

    app = FastAPI(title="fingertips MCP Server", lifespan=lifespan)

    # CORS：允许前端跨域调用 ping
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载 MCP Streamable HTTP endpoint → /mcp
    app.mount("/mcp", mcp_asgi)

    @app.post("/api/typing/ping")
    def typing_ping():
        """前端探针：用户正在打字时每隔几秒调用一次。"""
        store.ping()
        return {"ok": True}

    @app.get("/api/rhythm/status")
    def http_rhythm_status():
        """HTTP 方式查看当前节奏状态（调试用）。"""
        return store.peek()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# 4. 多进程辅助（both 模式）
# ---------------------------------------------------------------------------
def _run_stdio(state_file: str):
    global store
    store = RhythmStore(state_file=state_file)
    mcp.run(transport="stdio")


def _run_http(state_file: str, host: str, port: int):
    global store
    store = RhythmStore(state_file=state_file)
    import uvicorn
    app = create_http_app()
    uvicorn.run(app, host=host, port=port)


# ---------------------------------------------------------------------------
# 5. 启动入口
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="fingertips MCP Server")
    ap.add_argument(
        "--transport", choices=["stdio", "http", "both"], default="stdio",
        help="stdio=本地MCP客户端  http=远程HTTP服务  both=同时跑两者（Termux推荐）"
    )
    ap.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址")
    ap.add_argument("--port", type=int, default=8000, help="HTTP 监听端口")
    ap.add_argument("--state-file", default=STATE_FILE, help="状态文件路径")
    args = ap.parse_args()

    global store
    store = RhythmStore(state_file=args.state_file)

    if args.transport == "stdio":
        mcp.run(transport="stdio")

    elif args.transport == "http":
        import uvicorn
        app = create_http_app()
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.transport == "both":
        # Termux 推荐：stdio 给 Claude Desktop，HTTP 给前端探针
        # 两个进程通过文件共享状态
        ctx = multiprocessing.get_context("spawn")
        p_stdio = ctx.Process(target=_run_stdio, args=(args.state_file,))
        p_http = ctx.Process(target=_run_http, args=(args.state_file, args.host, args.port))
        p_stdio.start()
        p_http.start()
        try:
            p_stdio.join()
        except KeyboardInterrupt:
            p_stdio.terminate()
            p_http.terminate()
            p_stdio.join()
            p_http.join()


if __name__ == "__main__":
    main()
