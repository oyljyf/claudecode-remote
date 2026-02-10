# Slack 支持实现计划

- Version: 1.0.0
- Updated at: 2026-02-10 09:55:33
- Status: 📝 Planning

---

## Context

claudecode-remote 当前仅支持 Telegram。本计划添加 Slack 支持，实现完全相同的功能，同时保持 Telegram 不变。这是**增量添加**而非替换。

**设计决策：**
- 连接方式：HTTP Events API（复用 cloudflared 隧道）
- 交互方式：DM + /command 语法（与 Telegram 一致）
- 依赖策略：零外部依赖（stdlib `urllib.request` 调 Slack API）

---

## Architecture: Adapter Pattern

将平台特定代码隔离到 adapter 层，业务逻辑（tmux/session）保持不变。

```
                          ┌─────────────────┐
                          │   bridge.py     │
                          │  (业务逻辑)     │
                          │  tmux/session   │
                          └────────┬────────┘
                                   │ uses adapter interface
                    ┌──────────────┴──────────────┐
            ┌───────▼───────┐            ┌───────▼───────┐
            │TelegramAdapter│            │ SlackAdapter  │
            │ (extracted)   │            │ (new)         │
            └───────────────┘            └───────────────┘

Webhook routing (same cloudflared tunnel):
  /                    → Telegram webhook (backward compat)
  /slack/events        → Slack Events API
  /slack/interactions  → Slack Block Kit button callbacks
```

Hook scripts:
```
shell wrapper → hooks/lib/messaging.py (dispatcher)
                     ├── telegram_utils.py (existing)
                     └── slack_utils.py (new)
```

---

## Telegram vs Slack 关键差异

| 方面         | Telegram                                  | Slack                          |
| ------------ | ----------------------------------------- | ------------------------------ |
| API 认证     | URL 含 token                              | `Authorization: Bearer` header |
| 消息格式     | HTML (`parse_mode`)                       | mrkdwn + Block Kit             |
| 按钮         | `inline_keyboard` + `callback_data` (64B) | Block Kit `action_id` (255B)   |
| 回调确认     | `answerCallbackQuery` API                 | HTTP 200 即确认                |
| Typing       | `sendChatAction` 每 4s                    | 无原生 bot typing API          |
| 请求验证     | 无                                        | HMAC-SHA256 签名必须验证       |
| 消息长度     | 4096 字符                                 | 4000 字符（推荐）              |
| Session 绑定 | chat_id (数字)                            | channel_id (D 开头)            |
| 项目哈希     | 8-char MD5（64B 限制）                    | 不需要（255B action_id）       |

---

## Phase 1: Adapter 抽象层（仅重构，无 Slack 功能）

**目标：** 从 bridge.py 提取 Telegram 代码到 adapter，全量测试必须通过。

### 新建文件

| 文件                     | 职责                                                     |
| ------------------------ | -------------------------------------------------------- |
| `adapters/__init__.py`   | Package init，导出 `MessagingAdapter`, `TelegramAdapter` |
| `adapters/base.py`       | 抽象接口                                                 |
| `adapters/telegram.py`   | 提取 Telegram 特定逻辑                                   |
| `hooks/lib/messaging.py` | 平台 dispatcher                                          |

### adapters/base.py 接口定义

```python
from abc import ABC, abstractmethod

class MessagingAdapter(ABC):
    """平台消息适配器抽象基类"""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台标识符: 'telegram' | 'slack'"""

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """单条消息最大字符数"""

    @abstractmethod
    def send_message(self, chat_id: str, text: str,
                     parse_mode: str = None,
                     reply_markup: dict = None) -> dict:
        """发送文本消息，返回 API 响应"""

    @abstractmethod
    def send_typing(self, chat_id: str) -> None:
        """发送 typing 指示器"""

    @abstractmethod
    def answer_callback(self, callback_id: str, text: str = None) -> None:
        """确认按钮回调"""

    @abstractmethod
    def setup(self) -> None:
        """平台初始化（注册命令等）"""

    @abstractmethod
    def format_text(self, markdown: str) -> str:
        """Markdown → 平台原生格式"""

    @abstractmethod
    def make_button_grid(self, buttons: list[list[dict]]) -> dict:
        """构造平台原生按钮布局
        buttons: [[{"text": "label", "callback_data": "data"}, ...], ...]
        """

    @abstractmethod
    def make_url_button(self, text: str, url: str) -> dict:
        """构造 URL 按钮"""
```

### adapters/telegram.py 提取内容

从 bridge.py 提取以下函数/逻辑：

| 来源 (bridge.py)                                                 | 目标 (telegram.py)                                                     |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `telegram_api(method, data)` L169-182                            | `TelegramAdapter._api()`                                               |
| `setup_bot_commands()` L185-188                                  | `TelegramAdapter.setup()`                                              |
| `send_typing_loop(chat_id)` L191-194                             | `TelegramAdapter.send_typing()`                                        |
| inline keyboard 构造（散布在 handle_callback/handle_message 中） | `TelegramAdapter.make_button_grid()`                                   |
| `project_hash()` / `project_from_hash()` L79-88                  | `TelegramAdapter` 内部方法（callback_data 64B 限制是 Telegram 特有的） |
| `markdown_to_telegram_html` 调用                                 | `TelegramAdapter.format_text()`                                        |

### hooks/lib/messaging.py dispatcher

```python
"""平台消息 dispatcher：根据 ACTIVE_PLATFORM 路由到 telegram_utils 或 slack_utils"""

import os

def get_platform():
    return os.environ.get("ACTIVE_PLATFORM", "telegram")

def send_message(chat_id, token, text, parse_mode=None, reply_markup=None):
    platform = get_platform()
    if platform == "slack" or platform == "both":
        from . import slack_utils
        slack_utils.send_slack(chat_id, token, text)
    if platform == "telegram" or platform == "both":
        from . import telegram_utils
        telegram_utils.send_telegram(chat_id, token, text, parse_mode, reply_markup)

def format_markdown(text):
    platform = get_platform()
    if platform == "slack":
        from . import slack_utils
        return slack_utils.markdown_to_mrkdwn(text)
    else:
        from . import telegram_utils
        return telegram_utils.markdown_to_telegram_html(text)
```

### bridge.py 修改

- 导入 adapter：`from adapters import TelegramAdapter, SlackAdapter`
- `Handler.__init__` 接收 adapter 实例
- `handle_message()` / `handle_callback()` 中的 `telegram_api()` 调用替换为 `self.adapter.send_message()` 等
- `send_typing_loop()` 使用 `self.adapter.send_typing()`
- 按钮构造替换为 `self.adapter.make_button_grid()`
- `main()` 根据配置实例化 adapter，传给 Handler

### hook 模块修改

| 文件                             | 变更                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| `hooks/lib/send_response.py`     | `from messaging import send_message, format_markdown` 替代直接导入 `telegram_utils` |
| `hooks/lib/send_input.py`        | 同上                                                                                |
| `hooks/lib/handle_permission.py` | 同上，按钮通过 `messaging.make_buttons()` 构造                                      |

### 验证

- 全部现有测试通过（行为不变）
- 新增 adapter 接口合规测试（~15 tests）

---

## Phase 2: Slack Adapter 实现

**目标：** 实现 Slack 消息收发、按钮交互、权限控制。

### 新建文件

| 文件                               | 职责                                   |
| ---------------------------------- | -------------------------------------- |
| `adapters/slack.py`                | `SlackAdapter` 实现                    |
| `hooks/lib/slack_utils.py`         | `send_slack()`, `markdown_to_mrkdwn()` |
| `tests/test_slack_adapter.py`      | ~20 tests                              |
| `tests/test_slack_utils.py`        | ~15 tests                              |
| `tests/test_messaging_dispatch.py` | ~12 tests                              |

### adapters/slack.py 实现细节

```python
class SlackAdapter(MessagingAdapter):
    def __init__(self, bot_token: str, signing_secret: str):
        self.bot_token = bot_token
        self.signing_secret = signing_secret

    @property
    def platform_name(self) -> str:
        return "slack"

    @property
    def max_message_length(self) -> int:
        return 4000

    def _api(self, method: str, data: dict) -> dict:
        """调用 https://slack.com/api/{method}
        认证: Authorization: Bearer {bot_token}
        Content-Type: application/json; charset=utf-8
        """

    def send_message(self, channel_id, text, parse_mode=None, reply_markup=None):
        """chat.postMessage: channel, text, blocks (optional)"""

    def send_typing(self, channel_id):
        """Slack 无原生 bot typing API，可选发 placeholder 消息后删除"""
        pass  # no-op or optional placeholder

    def answer_callback(self, callback_id, text=None):
        """Slack Block Kit 回调通过 HTTP 200 确认，无需额外 API 调用"""
        pass

    def setup(self):
        """Slack 不支持 API 注册命令（需手动在 App Dashboard 设置）"""
        pass

    def format_text(self, markdown):
        """Markdown → Slack mrkdwn"""
        from hooks.lib.slack_utils import markdown_to_mrkdwn
        return markdown_to_mrkdwn(markdown)

    def make_button_grid(self, buttons):
        """构造 Block Kit actions block
        输入: [[{"text": "Allow", "callback_data": "perm_allow:xxx"}]]
        输出: {"blocks": [{"type": "actions", "elements": [...]}]}
        """

    def verify_signature(self, timestamp, body, signature):
        """HMAC-SHA256 签名验证
        v0={hmac_sha256(signing_secret, f'v0:{timestamp}:{body}')}
        """
```

### hooks/lib/slack_utils.py

```python
"""Slack 消息工具：零外部依赖"""

MAX_MESSAGE_LENGTH = 4000

def markdown_to_mrkdwn(text: str) -> str:
    """Markdown → Slack mrkdwn 转换
    - **bold** → *bold*
    - *italic* → _italic_
    - ```code``` → ```code```（保持不变）
    - `inline` → `inline`（保持不变）
    - HTML entities 转义（&, <, >）
    """

def send_slack(channel_id: str, token: str, text: str,
               blocks: list = None) -> bool:
    """发送 Slack 消息
    API: https://slack.com/api/chat.postMessage
    Headers: Authorization: Bearer {token}
    """

def log_message(log_file: str, text: str, role: str = "Claude") -> None:
    """复用 telegram_utils 同签名（或提取为通用函数）"""

def log_debug(debug_log: str, msg: str) -> None:
    """复用 telegram_utils 同签名"""
```

### bridge.py do_POST 路由修改

```python
def do_POST(self):
    path = self.path

    if path == "/slack/events":
        # Slack Events API
        data = json.loads(body)
        # url_verification challenge
        if data.get("type") == "url_verification":
            self._respond_json({"challenge": data["challenge"]})
            return
        # 验证签名
        if not self.server.slack_adapter.verify_signature(...):
            self.send_error(403)
            return
        # 处理 event
        event = data.get("event", {})
        if event.get("type") == "message" and not event.get("bot_id"):
            self.handle_slack_message(event)
        self._respond(200)

    elif path == "/slack/interactions":
        # Slack Block Kit 按钮回调
        # Content-Type: application/x-www-form-urlencoded
        payload = json.loads(parse_qs(body)["payload"][0])
        # 验证签名
        actions = payload.get("actions", [])
        for action in actions:
            self.handle_slack_action(action, payload)
        self._respond(200)

    else:
        # Telegram webhook（不变，向后兼容）
        # 现有逻辑...
```

### Slack 命令处理

Slack DM 中的 `/command` 消息作为普通 `message.im` 事件到达（因为是 DM 中的文本，不是 Slack slash command）。处理逻辑与 Telegram `handle_message` 相同：

```python
def handle_slack_message(self, event):
    """处理 Slack DM 消息"""
    channel_id = event["channel"]  # D 开头
    text = event.get("text", "")

    if text.startswith("/"):
        # 命令处理（复用相同的业务逻辑）
        self._dispatch_command(text, channel_id, platform="slack")
    else:
        # 普通消息转发到 tmux
        self._forward_to_tmux(text, channel_id, platform="slack")
```

### Slack 按钮交互

```python
def handle_slack_action(self, action, payload):
    """处理 Block Kit 按钮点击"""
    action_id = action["action_id"]  # 如 "perm_allow:abc12345"
    channel_id = payload["channel"]["id"]

    if action_id.startswith("perm_allow:") or action_id.startswith("perm_deny:"):
        self._handle_permission_response(channel_id, action_id)
    elif action_id.startswith("resume:"):
        # 恢复会话
    elif action_id == "continue_recent":
        # 继续最近会话
    # ...
```

### 修改文件

| 文件                     | 变更                                                           |
| ------------------------ | -------------------------------------------------------------- |
| `bridge.py` `do_POST()`  | 按 URL path 路由                                               |
| `bridge.py` `main()`     | 根据 config 实例化 SlackAdapter                                |
| `hooks/lib/common.sh`    | 添加 `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `ACTIVE_PLATFORM`  |
| `hooks/lib/messaging.py` | 添加 Slack dispatch 路径                                       |
| hook shell wrappers (×3) | 传递 `$ACTIVE_PLATFORM` `$SLACK_BOT_TOKEN` `$SLACK_CHANNEL_ID` |

### 新增测试

| 测试文件                           | 测试数 | 覆盖内容                                               |
| ---------------------------------- | ------ | ------------------------------------------------------ |
| `tests/test_slack_adapter.py`      | ~20    | API 格式、按钮构造、签名验证、mrkdwn 转换              |
| `tests/test_slack_utils.py`        | ~15    | `send_slack()`、`markdown_to_mrkdwn()`、转义、截断     |
| `tests/test_messaging_dispatch.py` | ~12    | platform 路由、`both` 模式、缺失 token 时 skip         |
| `tests/test_handler.py` (扩展)     | ~10    | Slack event routing、challenge、DM 命令、block_actions |

### 验证

- `ACTIVE_PLATFORM=telegram` 时行为与重构前完全一致
- Mock Slack API 测试全部通过
- Telegram 现有测试 100% 无回归

---

## Phase 3: 双平台基础设施

**目标：** 安装脚本、配置、状态文件支持双平台。

### 修改文件

| 文件                    | 变更                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| `config.env`            | 添加 `DEFAULT_PLATFORM=telegram`                                                                 |
| `scripts/install.sh`    | `--platform telegram\|slack\|both` 选项；Slack 引导创建 App、输入 `xoxb-` token + signing secret |
| `scripts/start.sh`      | Slack: 打印 tunnel URL 引导用户在 App Dashboard 设置 Event Subscriptions 和 Interactivity URL    |
| `scripts/uninstall.sh`  | 添加 `--slack` 选项（与 `--telegram` 平行）                                                      |
| `scripts/lib/common.sh` | 添加 `SLACK_CHANNEL_FILE` 等路径变量                                                             |

### install.sh Slack 流程

```bash
if [ "$PLATFORM" = "slack" ] || [ "$PLATFORM" = "both" ]; then
    print_step "Slack Bot Token (xoxb-...)"
    read -r SLACK_BOT_TOKEN
    print_step "Slack Signing Secret"
    read -r SLACK_SIGNING_SECRET
    # 写入 hooks/lib/common.sh（已安装的副本）
    # 引导：在 Slack App Dashboard 中：
    #   1. Bot Token Scopes: chat:write, im:read, im:write, im:history
    #   2. Event Subscriptions: message.im
    #   3. Interactivity: enable
fi
```

### start.sh Slack 特殊处理

Slack 不支持通过 API 设置 webhook URL（与 Telegram `setWebhook` 不同）。start.sh 需要：
1. 启动 cloudflared tunnel
2. 获取 tunnel URL
3. 打印引导信息：
   ```
   请在 Slack App Dashboard 中设置：
   Event Subscriptions URL: {tunnel_url}/slack/events
   Interactivity URL:       {tunnel_url}/slack/interactions
   ```

### 状态文件策略

| 现有文件                 | 保留 | Slack 对应              | 说明                                 |
| ------------------------ | ---- | ----------------------- | ------------------------------------ |
| `telegram_chat_id`       | 是   | `slack_channel_id`      | 各平台独立的全局 ID                  |
| `telegram_pending`       | 是   | `slack_pending`         | 各平台独立的消息处理标记             |
| `telegram_sync_paused`   | 是   | `sync_paused`（通用）   | 同步标志对所有平台生效               |
| `telegram_sync_disabled` | 是   | `sync_disabled`（通用） | 控制 Claude session 状态，非平台状态 |
| `session_chat_map.json`  | 扩展 | 多平台格式              | 见下方                               |

### session_chat_map.json 格式演进

**现有格式：**
```json
{"session_id_1": "123456789", "session_id_2": "987654321"}
```

**新格式（向后兼容）：**
```json
{
  "session_id_1": {"telegram": "123456789", "slack": "D0123ABCDE"},
  "session_id_2": "987654321"
}
```

读取逻辑：如果值是字符串，视为 telegram chat_id（向后兼容）；如果是 dict，按平台取值。

### 新增测试 (~15)

- install.sh `--platform` 选项解析
- start.sh Slack URL 引导输出
- session_chat_map 新旧格式兼容
- sync 标志通用化
- uninstall.sh `--slack` 选项

---

## Phase 4: 文档

### 修改文件

| 文件           | 变更                                                                            |
| -------------- | ------------------------------------------------------------------------------- |
| `CLAUDE.md`    | 架构图（添加 adapter 层）、组件表（添加 Slack 文件）、消息流（添加 Slack 路径） |
| `README.md`    | 添加 Slack 设置章节、双平台说明                                                 |
| `README_CN.md` | 同上（中文）                                                                    |

### 新建文件

| 文件                  | 内容               |
| --------------------- | ------------------ |
| `docs/slack-setup.md` | Slack App 创建指南 |

### docs/slack-setup.md 大纲

1. **创建 Slack App** — https://api.slack.com/apps → Create New App → From scratch
2. **Bot Token Scopes** — `chat:write`, `im:read`, `im:write`, `im:history`
3. **安装到 Workspace** — Install App → 获取 `xoxb-` token
4. **Event Subscriptions** — Enable → Request URL: `{tunnel_url}/slack/events` → Subscribe: `message.im`
5. **Interactivity** — Enable → Request URL: `{tunnel_url}/slack/interactions`
6. **Signing Secret** — Basic Information → App Credentials → Signing Secret
7. **运行** — `./scripts/install.sh --platform slack` → `./scripts/start.sh`

---

## 功能对照总览

| 功能                                 | Telegram               | Slack                      |
| ------------------------------------ | ---------------------- | -------------------------- |
| 12 个命令 (/start /stop /resume ...) | DM 中 /command         | DM 中 /command（相同语法） |
| 权限按钮 (Allow/Deny)                | inline_keyboard        | Block Kit buttons          |
| 权限 IPC                             | 文件 IPC（不变）       | 文件 IPC（不变）           |
| Typing 指示                          | sendChatAction 每 4s   | no-op（无原生 API）        |
| Session 绑定                         | chat_id (数字)         | channel_id (D 开头)        |
| 项目哈希                             | 8-char MD5（64B 限制） | 不需要（255B action_id）   |
| 消息格式                             | Markdown → HTML        | Markdown → mrkdwn          |
| 消息长度                             | 4096 字符              | 4000 字符                  |
| 请求验证                             | 无                     | HMAC-SHA256                |

---

## 估算

| Phase             | 新文件 | 改文件 | 新测试数 |
| ----------------- | ------ | ------ | -------- |
| 1: Adapter 抽象   | 4      | 5      | ~15      |
| 2: Slack 实现     | 5      | 6      | ~57      |
| 3: 双平台基础设施 | 0      | 5      | ~15      |
| 4: 文档           | 1      | 3      | 0        |
| **合计**          | **10** | **19** | **~87**  |

---

## Verification

每个 Phase 完成后：
```bash
.venv/bin/python -m pytest tests/ -v          # 全量测试
# CLAUDE.md pre-commit 安全检查 (5 项 grep)
```

Phase 2 额外验证：
- `ACTIVE_PLATFORM=telegram` 时行为与重构前完全一致
- Mock Slack API 测试全部通过
- Telegram 现有测试 100% 无回归
