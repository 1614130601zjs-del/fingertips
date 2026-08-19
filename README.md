# fingertips MCP Server

把 [fingertips](https://github.com/eveacla11/fingertips) 包装成 **MCP (Model Context Protocol)** 服务器，让任何 MCP 客户端都能感知你打字的犹豫。

## 暴露的 MCP Tools

| Tool | 说明 |
|------|------|
| `get_typing_status` | TA 此刻是否在打字 |
| `get_message_rhythm` | 最近一条消息的斟酌痕迹（打了多久、停了几次） |
| `check_unsent_thoughts` | 是否有欲言又止（打了又删的内容） |
| `get_full_rhythm_context` | 完整节奏上下文，可直接拼进 LLM 提示词 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 前端探针

把以下代码放进你的聊天输入框逻辑里（只上报"正在打字"这个事实，不携带任何内容）：

```javascript
// 根据部署方式修改 URL
const PING_URL = "http://localhost:8000/api/typing/ping";  // 本机
// const PING_URL = "https://your-app.onrender.com/api/typing/ping";  // Render

let _lastPing = 0;
inputEl.addEventListener("input", () => {
  const now = Date.now();
  if (now - _lastPing < 4000) return;
  if (!inputEl.value.trim()) return;
  _lastPing = now;
  fetch(PING_URL, { method: "POST", keepalive: true }).catch(() => {});
});
```

---

## 部署方式一：Termux 本机

适合在 Android 手机上本地运行，配合 Claude Desktop / Cursor 等 MCP 客户端。

### 安装环境

```bash
pkg update
pkg install python python-pip git
pip install -r requirements.txt
```

### 模式 A：只跑 stdio（适合 Claude Desktop）

```bash
python server.py --transport stdio --state-file ~/fingertips_state.json
```

Claude Desktop 配置 (`~/Library/Application Support/Claude/claude_desktop_config.json` 或对应平台路径)：

```json
{
  "mcpServers": {
    "fingertips": {
      "command": "python",
      "args": [
        "/data/data/com.termux/files/home/fingertips-mcp/server.py",
        "--transport", "stdio",
        "--state-file", "/data/data/com.termux/files/home/fingertips_state.json"
      ]
    }
  }
}
```

> ⚠️ 纯 stdio 模式下**没有 HTTP 端点**，前端探针需要另想办法（比如通过 Termux:API 或直接写入状态文件）。

### 模式 B：只跑 HTTP（适合支持 HTTP 的 MCP 客户端）

```bash
python server.py --transport http --port 8000 --state-file ~/fingertips_state.json
```

MCP 客户端连接：`http://localhost:8000/mcp`

前端探针 ping：`http://localhost:8000/api/typing/ping`

### 模式 C：both（推荐 ⭐）

同时跑 stdio（给 Claude Desktop）+ HTTP（给前端探针），两个进程共享同一个状态文件：

```bash
python server.py --transport both --port 8000 --state-file ~/fingertips_state.json
```

- MCP 客户端通过 stdio 连接
- 前端通过 `http://localhost:8000/api/typing/ping` 上报打字节奏

---

## 部署方式二：Render HTTPS

适合远程部署，任何有网络的地方都能接入。

### 一键部署

1. Fork 或上传本项目到 GitHub
2. 在 [Render](https://render.com) 创建 New Web Service
3. 选择你的仓库，Render 会自动读取 `render.yaml`
4. 部署完成后，获得 `https://your-app.onrender.com`

### 手动部署

如果没有 `render.yaml`，在 Render Dashboard 中：

- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python server.py --transport http --port $PORT --state-file /tmp/fingertips_state.json`

### 前端探针（Render）

```javascript
const PING_URL = "https://your-app.onrender.com/api/typing/ping";
```

### MCP 客户端连接（Render）

支持 Streamable HTTP 的 MCP 客户端（如 Cursor、部分 Web 客户端）：

```json
{
  "mcpServers": {
    "fingertips": {
      "type": "streamable-http",
      "url": "https://your-app.onrender.com/mcp"
    }
  }
}
```

> 如果你的客户端只支持 stdio，可以在本地跑一个桥接脚本，通过 HTTP 连接到 Render 上的 MCP 服务器，再以 stdio 方式暴露给客户端。

---

## 调参

通过环境变量或修改 `RhythmStore` 初始化参数：

| 参数 | 默认 | 含义 |
|------|------|------|
| `orphan_after_sec` | 600 | 打完多久没动静，算"欲言又止" |
| `min_note_sec` | 20 | 打字超过多少秒才值得告诉 AI |
| `pause_gap_sec` | 15 | 输入间隔超过多少秒算一次"停顿" |

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `server.py` | MCP Server 主文件（内嵌 fingertips 核心，零额外依赖） |
| `requirements.txt` | Python 依赖 |
| `render.yaml` | Render 平台部署配置 |

---

## License

MIT（与 fingertips 原项目一致）
