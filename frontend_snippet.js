// fingertips 前端探针（全部代码就这几行）
// 放进你聊天输入框的逻辑里。只上报"正在打字"这个事实，不携带任何内容。
//
// inputEl = 你的输入框元素；/api/typing/ping = 你后端的接收端点（见 example_fastapi.py）

let _lastPing = 0;
inputEl.addEventListener("input", () => {
  const now = Date.now();
  if (now - _lastPing < 4000) return;      // 每4秒最多上报一次
  if (!inputEl.value.trim()) return;       // 空输入框不算在打字
  _lastPing = now;
  fetch("/api/typing/ping", { method: "POST", keepalive: true }).catch(() => {});
});
