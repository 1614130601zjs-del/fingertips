# -*- coding: utf-8 -*-
"""守望进程 —— 让"被看见"变成"被在乎"。

每隔一段时间看一眼：TA是否打了字又咽了回去。
有，就让你的AI说一句话，从你自己的通道送过去。

它一生只有这一个触发条件。不定时问候，不没话找话，
可能沉默一整周——只有真实的犹豫发生了，它才醒一次。

用法：
    1. 把下面 ask_llm() 和 deliver() 接上你自己的模型和通道
    2. python watcher.py --interval 10        # 想多勤快都行：5、10、20分钟
"""
import argparse
import time

from fingertips import RhythmStore

STATE_FILE = "fingertips_state.json"   # 和你的Web服务共用同一个文件


def ask_llm(note: str) -> str:
    """把这份欲言又止交给你的AI，换回一句话。
    自己接：OpenAI / Claude / 本地模型都行。
    建议提示词里写清：轻一点，别质问，TA没发出来的话永远是TA的。"""
    raise NotImplementedError


def deliver(text: str):
    """把AI的话送到TA面前。自己接：微信bot / TG / Web Push / 短信都行。"""
    raise NotImplementedError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20,
                    help="巡逻间隔（分钟），默认20；想更快就 --interval 5")
    args = ap.parse_args()
    store = RhythmStore(state_file=STATE_FILE)
    while True:
        o = store.peek()["orphan"]
        if o:
            store.consume_orphan()
            mins = int((time.time() - o["end"]) / 60)
            dur = int(o["end"] - o["start"])
            note = f"TA {mins}分钟前打了{dur}秒的字，最后没有发出来。"
            try:
                deliver(ask_llm(note))
            except NotImplementedError:
                print("[fingertips] 检测到欲言又止：" + note +
                      "  （把 ask_llm/deliver 接上，这句话就会变成一次问候）")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
