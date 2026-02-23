# Telegram Group-per-Project Plan

- Version: 2.0.0
- Updated at: 2026-02-23 05:46:39
- Status: 📝 Planning

---

## 背景与灵感

用户观察到有人用 **不同的 Telegram 群组 + Topics（话题）分隔不同 AI Agent 的会话**。
本计划将此模式应用于 claudecode-remote，实现三层映射。

---

## 核心映射：三层对应

```
┌──────────────────────┐      ┌──────────────────────┐
│    Telegram 侧        │      │    Claude Code 侧     │
├──────────────────────┤      ├──────────────────────┤
│                       │      │                       │
│  Group (侧边栏可见)   │ ──── │  Project (目录)       │
│   │                   │      │   │                   │
│   ├─ General Topic    │ ──── │   ├─ 项目级控制台     │
│   │   (命令/状态)     │      │   │   (/bind /status) │
│   │                   │      │   │                   │
│   ├─ Topic "Add auth" │ ──── │   ├─ Session abc123   │
│   │                   │      │   │                   │
│   ├─ Topic "Fix #42"  │ ──── │   ├─ Session def456   │
│   │                   │      │   │                   │
│   └─ Topic "Refactor" │ ──── │   └─ Session ghi789   │
│                       │      │                       │
└──────────────────────┘      └──────────────────────┘
```

| Telegram | Claude Code | 用户感知 |
|----------|-------------|---------|
| Group 名 | Project 目录名 | 侧边栏一眼看到所有项目 |
| Topic 名 | Session 描述 | 点进群组看到所有对话线程 |
| Topic 内消息 | Prompt / Response | 完整对话历史，可回溯 |

---

## 现状 vs 目标

### 现状

```
用户 DM ──→ bridge ──→ 单个 tmux pane
所有项目、所有 session 混在一个 DM 对话里
用 /projects + /resume 切换，容易搞混
```

### 目标

```
Telegram 侧边栏：
  📂 CCRBots (Folder)  ← Telegram 文件夹，收纳 bot + 所有项目群组
    ├─ 🤖 Bot DM             ← 控制台 / 旧模式兜底
    ├─ 📁 my-startup         ← Group（点进去看到多个 Topic）
    │   ├─ 💬 General        ← 项目控制台（/status, /bind）
    │   ├─ 💬 Add auth       ← Session 1（独立对话线程）
    │   └─ 💬 Fix login bug  ← Session 2（独立对话线程）
    └─ 📁 api-server         ← 另一个 Group
        ├─ 💬 General
        └─ 💬 DB migration
```

> **推荐**：在 Telegram 中创建一个 **文件夹（Folder）**（如 "CCRBots"），
> 把 Bot DM 和所有项目群组都拖进去。这样侧边栏只占一行，展开后看到所有项目。
> 设置方法：Telegram Settings → Folders → Create Folder → 添加 bot 和群组。

---

## Telegram Topics 技术基础

### 什么是 Topics

Telegram 超级群组可以开启 **论坛模式（Forum / Topics）**，群内消息按话题分组：
- 每个 Topic 是一个独立线程，有自己的 `message_thread_id`
- "General" 是默认 Topic，不能删除
- Bot 可以创建 Topic、发送消息到指定 Topic
- 用户在不同 Topic 发消息，bot 收到的 update 中带有 `message_thread_id`

### 关键 API

```
# Bot 创建 Topic
POST /createForumTopic
  chat_id: -1001234567890
  name: "Add auth feature"
  → 返回 { message_thread_id: 42 }

# Bot 发送消息到 Topic
POST /sendMessage
  chat_id: -1001234567890
  message_thread_id: 42
  text: "Claude 输出..."

# Bot 收到消息
update.message.message_thread_id = 42  ← 告诉你用户在哪个 Topic 说的话
```

---

## 数据模型

### 映射文件：`~/.claude/group_project_map.json`

```json
{
  "-1001234567890": {
    "project": "-Users-foo-Projects-my-startup",
    "project_path": "/Users/foo/Projects/my-startup",
    "tmux_window": "my-startup",
    "topics": {
      "abc12345-session-uuid": {
        "thread_id": 42,
        "name": "Add auth feature",
        "created": "2026-02-23T05:00:00"
      },
      "def67890-session-uuid": {
        "thread_id": 57,
        "name": "Fix login bug",
        "created": "2026-02-23T03:00:00"
      }
    }
  },
  "-1009876543210": {
    "project": "-Users-foo-work-api-server",
    "project_path": "/Users/foo/work/api-server",
    "tmux_window": "api-server",
    "topics": {}
  }
}
```

- 外层 key = `chat_id`（群组 ID，负数）
- `topics` 的 key = Claude Code `session_id`
- `thread_id` = Telegram Topic 的 `message_thread_id`

### 路由查找

```
入站：chat_id + thread_id → session_id → tmux window
出站：session_id → 查找所属 chat_id + thread_id → 发到对应 Topic
```

---

## 命令总览

| 命令 | 在哪用 | 作用 |
|------|--------|------|
| `/bind [path]` | Group General Topic | 绑定此群组到本地项目目录 |
| `/unbind` | Group General Topic | 解除绑定 |
| `/new [描述]` | Group 任意位置 | 创建新 Topic + 新 Claude Session |
| `/status` | Group General Topic | 显示项目绑定、活跃 session、tmux 状态 |
| `/groups` | DM | 列出所有已绑定群组 |

> 注意：现有 DM 命令（`/projects`, `/resume`, `/start`, `/stop` 等）全部保留。

---

## 详细场景

### 场景 1：首次设置（一次性）

```
┌─────────────────────────────────────────────────────────────────┐
│ 用户操作                       │ 说明                           │
├────────────────────────────────┼─────────────────────────────── │
│ 1. @BotFather → /setprivacy   │ 关闭隐私模式                   │
│    → 选 bot → Disable          │ 否则群组内收不到普通消息       │
│                                │                                │
│ 2. @BotFather → /setjoingroups│ 确保 bot 可被加入群组          │
│    → Enable                    │                                │
│                                │                                │
│ 3. Telegram Settings → Folders │ 创建文件夹统一管理             │
│    → Create Folder             │                                │
│    → 名称: "CCRBots"     │ 所有项目群组 + bot DM 放在     │
│    → 添加 bot DM               │ 同一个文件夹里，侧边栏整洁    │
└────────────────────────────────┴────────────────────────────────┘
```

**只需做一次，所有群组生效。**
**后续每创建一个项目群组，记得把它拖进 "CCRBots" 文件夹。**

---

### 场景 2：为新项目创建群组

**目标**：为 `~/Projects/my-startup` 创建专属 Telegram 群组

#### Step 1 — Telegram：创建群组

```
用户在 Telegram 中：
  1. "New Group" → 群组名: my-startup
  2. 添加 bot（搜索 @YourClaudeBot）
  3. 创建完成

  4. 进入群组设置 → "Topics" → 开启（变成 Forum 模式）
     ┌───────────────────────────────────┐
     │ ⚙ Group Settings                  │
     │                                    │
     │ Topics: [开启] ← 点这里            │
     │                                    │
     │ 开启后群组变成论坛模式，           │
     │ 消息按话题分组                     │
     └───────────────────────────────────┘

  5. 把群组拖进 "CCRBots" 文件夹
     （长按群组 → Move to Folder → CCRBots）
```

> **为什么开启 Topics？** 开启后每个 Claude session 成为独立线程，
> 不开启则退化为 v1 方案（一个群 = 一个项目，session 混在一起）。两种都支持。

#### Step 2 — Group General Topic：绑定项目

```
在 "General" Topic 中发送：

  /bind ~/Projects/my-startup

Bot 回复（在 General Topic 中）：
  ✅ Group → Project bound
  ─────────────────────────
  Group:   my-startup
  Path:    ~/Projects/my-startup
  Window:  tmux "my-startup" (created)

  Send /new to start a Claude session,
  or send a message here to start immediately.
```

**背后发生的事：**

```
1. Bridge 收到 chat_id=-1001234567890, thread_id=General
2. 展开路径 → /Users/foo/Projects/my-startup
3. 编码 → -Users-foo-Projects-my-startup
4. 写入 group_project_map.json
5. tmux new-window -t claude -n "my-startup" -c "/Users/foo/Projects/my-startup"
6. tmux send-keys ... "claude --dangerously-skip-permissions" Enter
```

#### Step 3 — 开始对话

**方式 A：直接在 General Topic 发消息**

```
在 General Topic 发送：
  帮我搭建 Next.js 项目框架

Bot 自动：
  1. 创建新 Topic "帮我搭建 Next.js 项目框架"（取消息前 30 字符为名）
  2. 在新 Topic 中回复：⚡ New session started
  3. Claude 的输出发到这个 Topic
```

**方式 B：先创建 Topic，再对话**

```
在 General Topic 发送：
  /new Add authentication

Bot：
  1. 创建 Topic "Add authentication"
  2. 在新 Topic 中回复：⚡ New session started
  3. 提示：Send your first message in this topic.

用户切到 "Add authentication" Topic：
  用 JWT 实现用户登录

Claude 回复（在同一 Topic 内）：
  好的，我来用 JWT 实现...
```

---

### 场景 3：为已有项目创建群组（有历史 session）

```
/bind ~/work/api-server

Bot 回复（在 General Topic 中）：
  ✅ Group → Project bound
  ─────────────────────────
  Group:   api-server
  Path:    ~/work/api-server

  📂 Found 3 existing sessions. Importing...
  ─────────────────────────
  Created Topic "DB migration" ← session abc123 (2h ago)
  Created Topic "Add caching"  ← session def456 (1d ago)
  Created Topic "Init project" ← session ghi789 (3d ago)

  Click any topic to continue that session,
  or /new to start fresh.
```

**背后发生的事：**

```
1. Bridge 扫描 ~/.claude/projects/-Users-foo-work-api-server/*.jsonl
2. 对每个有效 session，读取 JSONL 第一条消息的 prompt 作为 Topic 名
3. 调用 Telegram createForumTopic API 创建 Topic
4. 将 session_id → thread_id 写入 group_project_map.json
5. 用户点进某个 Topic 发消息 → bridge 检测到 thread_id → 找到 session_id → resume
```

---

### 场景 4：日常使用 — 在不同 Topic 间切换

```
用户 Telegram 侧边栏：

  📁 my-startup
    ├─ 💬 General          ← /status, /new 等命令
    ├─ 💬 Add auth         ← 点进去：这个 session 的完整对话
    ├─ 💬 Fix login bug    ← 点进去：另一个 session 的完整对话
    └─ 💬 Setup CI/CD      ← 正在进行中...

用户点击 "Add auth" Topic，发送：
  之前的 JWT 实现有 bug，token 过期后没有刷新

Bridge 处理：
  1. 收到 chat_id=-100123..., message_thread_id=42
  2. 查 group_project_map: thread_id=42 → session abc123
  3. tmux 当前 window 的 session 是 abc123？
     ├─ 是 → 直接 send-keys
     └─ 否 → claude --resume abc123（切换 session）→ 然后 send-keys
  4. Claude 输出 → hook → 查 session abc123 → thread_id=42 → 发到该 Topic
```

**关键体验**：用户只需要 **点击不同 Topic**，就能在不同 session 之间切换，
不需要发 `/resume` 命令或者记 session ID。

---

### 场景 5：在 Topic 中使用完整功能

**权限请求：**

```
Topic "Add auth" 中：

Bot（Claude 请求权限）：
  🔧 Claude wants to edit src/auth/jwt.ts
  ───────────────────────
  + import { verify } from 'jsonwebtoken'
  + export function validateToken(token: string) {
  ...
  [Allow] [Allow all] [Deny]

Alice 点击 [Allow]
Bot: ✅ Permission granted (by Alice)
```

> 权限请求和回复都在同一个 Topic 内，不会跑到别的 Topic。

**AskUserQuestion：**

```
Topic "Setup CI/CD" 中：

Bot（Claude 在问问题）：
  ❓ Which CI provider do you want to use?
  [GitHub Actions (Recommended)]
  [GitLab CI]
  [CircleCI]

Bob 点击 [GitHub Actions]
Bot: Using GitHub Actions...
```

**Alarm 声音：**

```
Claude 在 "Fix login bug" 完成 → play-alarm.sh done → 本地响声（不变）
Claude 在 "Add auth" 问问题 → play-alarm.sh alert → 本地响声（不变）
```

声音是本地的，与 Topic 路由无关。

---

### 场景 6：不开启 Topics 的群组（降级模式）

如果用户不想开启 Topics（更简单的方式）：

```
普通群组（无 Topics），所有消息在一个流中：

  /bind ~/Projects/my-startup

Bot: ✅ Bound (simple mode, no topics)

  帮我搭建项目
Bot: ✅ 好的...

  /resume
Bot: 📂 Sessions for my-startup
  [Session abc123 (10m ago)]
  [Session def456 (2d ago)]
  [🆕 New session]
```

**行为**：等同于 v1 方案（Group = Project，session 用命令切换）。
Bridge 检测 `update.message.is_topic_message`，若无则走降级逻辑。

---

### 场景 7：DM 管理所有群组

```
在 DM 中发送：

  /groups

Bot 回复：
  📋 Bound Groups
  ─────────────────────────
  1. 📁 my-startup → ~/Projects/my-startup
     Topics: 3 | Active: "Add auth" | Window: ✅
  2. 📁 api-server → ~/work/api-server
     Topics: 2 | Active: "DB migration" | Window: ✅
  3. 📁 docs → ~/work/docs
     Topics: 1 | Active: none | Window: ❌

  DM (this chat) → unbound, using /projects to switch
```

DM 作为 **控制台**：查看全局状态、管理绑定，但不是主要对话场所。

---

### 场景 8：解绑群组

```
在 General Topic 发送：

  /unbind

Bot:
  ⚠️ Unbind api-server?
  ─────────────────────────
  This will disconnect the group from ~/work/api-server.
  Topics and chat history in Telegram will be preserved.
  Claude sessions are not deleted.

  [Unbind] [Cancel]

用户点击 [Unbind]:
  ✅ Group unbound.
  tmux window "api-server" still running.
  [Stop window] [Keep running]
```

**解绑后**：
- Telegram 群组和 Topics 保留（只是聊天记录，不删除）
- Claude sessions 保留（磁盘上的 .jsonl 不变）
- `group_project_map.json` 中移除该条目
- 可以用 `/bind` 重新绑定（会重新导入 sessions 为 Topics）

---

### 场景 9：多人协作

```
群组 "my-startup"，成员：Alice（管理员）、Bob、Charlie

Topic "Add auth" 中：

Alice: 用 JWT 实现登录
Bot: 好的，我来实现...

Bob: （在同一个 Topic 中）等一下，加上 refresh token
Bot: 明白，我加上 refresh token...

Charlie: （开新 Topic）/new Fix deployment
Bot: → 创建 Topic "Fix deployment"，新 session 开始

Alice 在 "Add auth" 继续对话 → 不受 Charlie 影响
Charlie 在 "Fix deployment" 工作 → 独立的 session
```

**可选权限控制：**

| 配置 | 效果 |
|------|------|
| 不配置（默认） | 所有群组成员都可发消息和操作 |
| `ALLOWED_USER_IDS=123,456` | 只有指定用户可以发消息给 Claude |
| 群组管理员限制 | 只有管理员可以 `/bind`、`/unbind` |

---

### 场景 10：从 DM 迁移到群组

**老用户**：一直用 DM 模式，现在想迁移到群组

```
Step 1: 查看现有项目
  DM: /projects
  Bot: my-startup (3 sessions), api-server (5 sessions)

Step 2: 创建群组 "my-startup"，开启 Topics，添加 bot

Step 3: 绑定
  General Topic: /bind ~/Projects/my-startup
  Bot: ✅ Bound. Found 3 sessions. Importing as Topics...
    → "Add auth" (2h ago)
    → "Init project" (3d ago)
    → "DB setup" (5d ago)

Step 4: 验证
  点击 "Add auth" Topic → 发消息 → Claude 恢复该 session ✅
  DM 中发消息 → 仍然走旧逻辑 ✅

迁移零数据丢失：session_chat_map.json 保留，group_project_map.json 新增。
```

---

## 完整路由流程

### 入站：Telegram → tmux

```
消息到达 bridge (do_POST)
  │
  ├─ 有 chat_id + message_thread_id？
  │   │
  │   ├─ group_project_map 有该 chat_id？
  │   │   │
  │   │   ├─ 有 → 找到 project
  │   │   │   │
  │   │   │   ├─ thread_id 在 topics 中？
  │   │   │   │   ├─ 是 → 找到 session_id → resume（如需）→ send-keys
  │   │   │   │   └─ 否 → General Topic 消息
  │   │   │   │         ├─ 是命令 → 执行（/new, /status, /bind）
  │   │   │   │         └─ 是普通消息 → 自动创建 Topic + 新 session → send-keys
  │   │   │   │
  │   │   └─ 无 → 未绑定群组，忽略或提示 /bind
  │   │
  │   └─ 无 thread_id（普通群组，未开 Topics）
  │       └─ group_project_map 有 chat_id？
  │           ├─ 有 → 降级模式：直接 send-keys 到该项目的 tmux window
  │           └─ 无 → 忽略
  │
  └─ 只有 chat_id（DM）
      └─ 现有逻辑（session_chat_map + current_session_id）
```

### 出站：tmux → Telegram

```
Hook 触发（Claude 输出/权限请求/通知）
  │
  ├─ 读取 session_id（从 current_session_id 或 CLAUDE_SESSION_ID 环境变量）
  │
  ├─ 查 group_project_map.json：
  │   │ 遍历所有 chat_id → 检查 topics 中是否有该 session_id
  │   │
  │   ├─ 找到 → chat_id + thread_id
  │   │   └─ sendMessage(chat_id, message_thread_id=thread_id, text=...)
  │   │
  │   └─ 未找到 → 降级
  │       └─ 查 session_chat_map.json（旧逻辑）
  │           └─ sendMessage(chat_id, text=...)
  │
  └─ 均未找到 → 查 telegram_chat_id（全局 DM 兜底）
```

---

## 数据文件总览

| 文件 | 新增/保留 | 说明 |
|------|-----------|------|
| `~/.claude/group_project_map.json` | 新增 | `{chat_id: {project, topics: {session_id: thread_id}}}` |
| `~/.claude/session_chat_map.json` | 保留 | DM 模式旧逻辑兜底 |
| `~/.claude/current_session_id` | 保留 | Hook 使用，不变 |
| `~/.claude/telegram_chat_id` | 保留 | DM 全局兜底 |

---

## tmux 多 Window 模型

```
tmux session: claude
├── window 0: "main"        ← 原有（DM 模式的默认 window）
├── window 1: "my-startup"  ← 群组 my-startup 绑定
├── window 2: "api-server"  ← 群组 api-server 绑定
└── ...
```

- 每个群组绑定时创建一个 tmux window
- Window 名 = 项目目录末尾名（sanitized）
- 同一 window 内，通过 `claude --resume <session_id>` 切换 session
- 路由目标：`tmux send-keys -t claude:{window_name}`

---

## 实现方案

### Phase 1：数据层

```python
GROUP_PROJECT_MAP_FILE = CLAUDE_DIR / "group_project_map.json"

def load_group_project_map() -> dict:
    """Load {chat_id: {project, topics: {session_id: {thread_id, name}}}}."""

def save_group_project_map(mapping: dict) -> None:

def bind_group_to_project(chat_id: int, project_path: str) -> None:
    """Create group → project binding, create tmux window."""

def get_project_for_group(chat_id: int) -> dict | None:
    """Lookup: chat_id → {project, project_path, tmux_window, topics}."""

def get_group_for_session(session_id: str) -> tuple[int, int] | None:
    """Reverse lookup: session_id → (chat_id, thread_id) for outbound routing."""

def register_topic(chat_id: int, session_id: str, thread_id: int, name: str) -> None:
    """Add session → topic mapping."""
```

### Phase 2：Telegram Topic API

```python
def create_forum_topic(chat_id: int, name: str) -> int:
    """Call Telegram createForumTopic, return message_thread_id."""
    # POST https://api.telegram.org/bot{TOKEN}/createForumTopic
    # Returns: {"ok": true, "result": {"message_thread_id": 42, "name": "..."}}

def send_to_topic(chat_id: int, thread_id: int, text: str, **kwargs) -> None:
    """Send message to specific topic (sendMessage with message_thread_id)."""

def send_keyboard_to_topic(chat_id: int, thread_id: int, text: str, keyboard) -> None:
    """Send inline keyboard to specific topic."""
```

### Phase 3：命令处理

```python
def _cmd_bind(self, chat_id, thread_id, text):
    """
    /bind [path]
    - 只在 General Topic 或无 Topics 群组中响应
    - 解析路径（或从 tmux cwd 推断）
    - 检查路径存在
    - 写入 group_project_map
    - 创建 tmux window
    - 如有历史 session → 自动导入为 Topics
    """

def _cmd_new(self, chat_id, thread_id, text):
    """
    /new [描述]
    - 创建 Telegram Topic
    - 创建 Claude session
    - 注册 topic ↔ session 映射
    """

def _cmd_unbind(self, chat_id, thread_id, text):
    """移除 group → project 绑定"""

def _cmd_groups(self, chat_id, text):
    """DM 中使用，列出所有已绑定群组"""
```

### Phase 4：入站路由改造

```python
def _handle_group_message(self, chat_id, thread_id, text):
    """
    群组消息路由：
    1. chat_id → 查找绑定的 project
    2. thread_id → 查找绑定的 session_id
       - 找到 → resume + send-keys
       - General Topic + 普通消息 → 自动创建 Topic + 新 session
    3. 发到对应 tmux window
    """
```

### Phase 5：出站路由改造

```bash
# Hook 修改（send-to-telegram.sh）
# 新增查找逻辑：
SESSION_ID=...
# 1. 尝试 group_project_map：session → (chat_id, thread_id)
# 2. 若找到 → sendMessage with message_thread_id
# 3. 若未找到 → 旧逻辑（session_chat_map / telegram_chat_id）
```

---

## 两种模式对比

| 特性 | DM 模式（现有） | 群组模式（新增） | 群组 + Topics 模式（推荐） |
|------|----------------|-----------------|--------------------------|
| 项目隔离 | ❌ 全在一个 DM | ✅ 一群一项目 | ✅ 一群一项目 |
| Session 隔离 | ❌ 命令切换 | ❌ 命令切换 | ✅ 一 Topic 一 Session |
| 可视性 | 差 | 中 | 好（侧边栏 + Topic 列表） |
| 多人协作 | ❌ | ✅ | ✅（且各 session 独立） |
| 设置复杂度 | 低 | 中 | 中（多一步开 Topics） |
| 向后兼容 | — | ✅ DM 不受影响 | ✅ DM 不受影响 |

---

## 影响范围

| 文件 | 修改内容 |
|------|---------|
| `bridge.py` | 新增 ~8 个函数；群组路由逻辑；Topic API 调用 |
| `hooks/send-to-telegram.sh` | 出站路由新增 group_project_map 查询 + thread_id |
| `hooks/handle-permission.sh` | 同上（权限弹窗路由到 Topic） |
| `hooks/send-notification-to-telegram.sh` | 同上（通知路由到 Topic） |
| `hooks/lib/common.sh` | 新增 `GROUP_PROJECT_MAP` 路径变量 |
| `config.env` | 无需改动（群组绑定是运行时动态的） |
| `CLAUDE.md` | 新增函数/命令文档 |
| `README.md` / `README_CN.md` | 新增"群组模式"章节 |
| `docs/usage.md` | 补充群组创建和绑定步骤 |
| `tests/` | 新增 `test_group_project.py` |

---

## 测试计划

| 场景 | 验证点 |
|------|--------|
| `/bind` 在群组 General Topic | 写入 group_project_map，创建 tmux window |
| `/bind` 带路径 | 路径展开正确，编码正确 |
| `/bind` 不带路径 | 取 tmux cwd |
| `/bind` 已有项目 | 历史 session 导入为 Topics |
| `/new` 创建 Topic | Telegram Topic 创建，session 启动，映射写入 |
| Topic 内发消息 | 路由到正确 session，输出回到同一 Topic |
| General Topic 发普通消息 | 自动创建 Topic + session |
| 不同 Topic 切换 | tmux 内 resume 正确 session |
| 出站路由 | Hook 发到正确的 chat_id + thread_id |
| 无 Topics 群组（降级） | 走简单群组模式 |
| DM 不受影响 | 旧逻辑正常工作 |
| `/unbind` | 移除映射，Telegram 数据保留 |
| `/groups` | DM 中列出所有绑定 |
| 多群组同时活跃 | 消息互不串扰 |

---

## 实现优先级

```
Phase 1（数据层）        ── 基础，不改变现有行为
Phase 2（Topic API）     ── Telegram API 封装
Phase 3（命令）          ── /bind, /new, /unbind, /groups
Phase 4（入站路由）      ── 群组消息自动路由到 session
Phase 5（出站路由）      ── Hook 输出路由到正确 Topic
```

---

## 注意事项

1. **开启 Topics 需要超级群组**：创建群组时 Telegram 可能会自动升级为超级群组，或手动在设置中开启
2. **Bot Privacy Mode 必须关闭**：否则群组中只能接收 `/command`，收不到普通消息
3. **群组 chat_id 为负数**（Telegram 规范），代码中统一用字符串存储
4. **Topic message_thread_id 是整数**，每个群组内唯一
5. **tmux window 名**需 sanitize（只保留字母数字和连字符）
6. **并发**：同一 tmux window 内只有一个 Claude 进程，切换 session 需要 resume
7. **Topic 名来源**：自动创建时取用户消息前 30 字符；`/new` 时取参数；导入时读 JSONL 首条 prompt
8. **向后兼容**：不开 Topics 的群组 = v1 简单模式；DM = 完全不变
