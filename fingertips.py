# -*- coding: utf-8 -*-
"""fingertips —— 指尖的语气

让你的 AI 感知到人打字的节奏：这条消息打了多久、中途停顿了几次、
以及最珍贵的那种——打了一段字，最后没有发出来。

铁律：只记节奏，永不记内容。
这个模块从设计上就不接触任何文本——它只见过时间戳。
你删掉的那句话是什么，没有任何人知道，包括这套系统。
"""
import json
import time
from pathlib import Path

PING_KEEP = 300          # 最多保留的ping数（防内存膨胀）


class RhythmStore:
    """打字节奏账本。

    参数都可调：
      orphan_after_sec  打完多久没动静，算"欲言又止"（默认10分钟）
      min_note_sec      打字超过多少秒才值得告诉AI（默认20秒，快问快答不打扰）
      pause_gap_sec     两次输入间隔超过多少秒算一次"停顿"（默认15秒）
      state_file        可选。给守望进程用：Web服务和守望进程是两个进程时，
                        用同一个文件共享状态；同进程内用可不传。
    """

    def __init__(self, orphan_after_sec=600, min_note_sec=20,
                 pause_gap_sec=15, state_file=None):
        self.orphan_after = orphan_after_sec
        self.min_note = min_note_sec
        self.pause_gap = pause_gap_sec
        self.state_file = Path(state_file) if state_file else None
        self.pings = []
        self.orphan = None
        self._load()

    # ---------- 状态持久化（可选） ----------
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

    # ---------- 内部 ----------
    def _gc(self):
        """一段打字搁置太久没发 → 沉为"欲言又止"的痕迹。"""
        if self.pings and time.time() - self.pings[-1] > self.orphan_after:
            if self.pings[-1] - self.pings[0] >= 5:   # 太短的不算，可能只是误触
                self.orphan = {"start": self.pings[0], "end": self.pings[-1]}
            self.pings.clear()

    # ---------- 三个入口 ----------
    def ping(self):
        """前端正在打字时每隔几秒调一次（见 frontend_snippet.js）。"""
        self._load()
        self._gc()
        self.pings.append(time.time())
        del self.pings[:-PING_KEEP]
        self._save()

    def pop_note(self) -> str:
        """消息发出时调用：结算打字节奏，返回给AI看的一句话（多数时候为空串）。

        把返回值拼进你发给LLM的上下文即可，建议加一句嘱咐：
        「以下是TA打这条消息的节奏，供感受，别复述数字。」
        """
        self._load()
        self._gc()
        notes = []
        if self.orphan:
            mins = int((time.time() - self.orphan["end"]) / 60)
            dur = int(self.orphan["end"] - self.orphan["start"])
            notes.append(f"TA {mins}分钟前打过{dur}秒的字，那条没有发出来"
                         "（打了什么无人知晓，包括系统）")
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
        """守望进程用：看一眼当前状态（不消费）。
        返回 {"typing_now": bool, "orphan": {...}|None}
        """
        self._load()
        self._gc()
        self._save()
        return {
            "typing_now": bool(self.pings and time.time() - self.pings[-1] < 300),
            "orphan": dict(self.orphan) if self.orphan else None,
        }

    def consume_orphan(self):
        """守望进程处理完欲言又止后调用，避免重复问候。"""
        self._load()
        o, self.orphan = self.orphan, None
        self._save()
        return o
