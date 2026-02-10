# 使用场景指南

## 目录

- [使用场景指南](#使用场景指南)
  - [目录](#目录)
  - [概念说明](#概念说明)
    - [Session（对话）](#session对话)
    - [同步方向](#同步方向)
    - [共享机制](#共享机制)
    - [自动绑定](#自动绑定)
- [Telegram 端场景](#telegram-端场景)
  - [场景 1：首次连接 Telegram](#场景-1首次连接-telegram)
  - [场景 2：外出时用 Telegram 继续工作](#场景-2外出时用-telegram-继续工作)
  - [场景 3：从 Telegram 切换 Session](#场景-3从-telegram-切换-session)
    - [方法 A：选择列表](#方法-a选择列表)
    - [方法 B：快速恢复](#方法-b快速恢复)
  - [场景 4：从 Telegram 切换 Project](#场景-4从-telegram-切换-project)
  - [场景 5：从 Telegram 暂停同步](#场景-5从-telegram-暂停同步)
  - [场景 6：从 Telegram 中断 Claude](#场景-6从-telegram-中断-claude)
  - [场景 7：从 Telegram 彻底断开](#场景-7从-telegram-彻底断开)
  - [场景 8：从 Telegram 重连](#场景-8从-telegram-重连)
    - [新建对话](#新建对话)
    - [恢复已有 session](#恢复已有-session)
    - [快速恢复最近 session](#快速恢复最近-session)
  - [场景 9：查看状态](#场景-9查看状态)
- [桌面端场景](#桌面端场景)
  - [场景 10：首次启动](#场景-10首次启动)
  - [场景 11：日常使用（桌面为主）](#场景-11日常使用桌面为主)
  - [场景 12：重启 Bridge](#场景-12重启-bridge)
  - [场景 13：查看 Claude 输出](#场景-13查看-claude-输出)
  - [场景 14：为不同项目创建 Session](#场景-14为不同项目创建-session)
  - [场景 15：从桌面断开同步](#场景-15从桌面断开同步)
  - [场景 16：更新 Hook 脚本](#场景-16更新-hook-脚本)
  - [场景 17：完全停止服务](#场景-17完全停止服务)
  - [命令速查](#命令速查)
  - [常见问题](#常见问题)
    - [Q: 切换 session 后桌面 Claude 断开了？](#q-切换-session-后桌面-claude-断开了)
    - [Q: 发消息提示 "Not bound"？](#q-发消息提示-not-bound)
    - [Q: `/stop` 和 `/escape` 有什么区别？](#q-stop-和-escape-有什么区别)
    - [Q: 切换到其他项目的 session 提示 "session not found"？](#q-切换到其他项目的-session-提示-session-not-found)
    - [Q: Telegram 命令没有更新（看不到新命令）？](#q-telegram-命令没有更新看不到新命令)
    - [Q: 如何更新 bot 命令但不重装？](#q-如何更新-bot-命令但不重装)

---

## 概念说明

### Session（对话）
每次与 Claude 的对话都有一个唯一session ID（UUID），存储在 `~/.claude/projects/<项目名>/<session-id>.jsonl`。

### 同步方向
- **桌面 → Telegram**：通过 Hook 脚本自动发送（Claude 每次回复和用户输入触发）
- **Telegram → 桌面**：通过 Bridge 转发到 tmux 中的 Claude 进程

### 共享机制
桌面和 Telegram 共享同一个 tmux 终端。你在 Telegram 发的消息，桌面能看到；Claude 在桌面的回复，Telegram 也能收到。

### 自动绑定
Bridge 具有自动绑定功能：
- 如果当前 session 未绑定到任何 chat，首条 Telegram 消息会自动绑定
- 后台 session 轮询器每 5 秒检测新 session 并自动绑定
- 无需手动执行 `/bind`（除非需要强制重绑）

---

# Telegram 端场景

## 场景 1：首次连接 Telegram

**前提**：桌面已运行 bridge（`./scripts/start.sh --new` 或 `./scripts/start.sh`）

1. 打开 Telegram bot 聊天
2. 直接发送一条消息

Bridge 会自动检测当前 session 并绑定。如果看到提示说需要绑定，发送 `/bind` 即可。

---

## 场景 2：外出时用 Telegram 继续工作

**目标**：从 Telegram 发消息给桌面的 Claude

**前提**：Bridge 已在桌面运行

1. 打开 Telegram bot 聊天
2. 直接发送消息即可

> 消息会注入到桌面 tmux 中的 Claude，Claude 的回复也会同步回 Telegram。

如果看到 "Not bound" 提示：
- 发送 `/bind` 绑定当前 session
- 或发送 `/continue` 连接到最近的 session

---

## 场景 3：从 Telegram 切换 Session

**目标**：切换 Claude 的对话（桌面自动跟随）

### 方法 A：选择列表
```
/resume
```
显示当前项目最近的 session 列表（完整 UUID + 时间），点击选择。

### 方法 B：快速恢复
```
/continue
```
直接恢复最近修改的 session。

> **注意**：切换 session 时桌面 Claude 会短暂重启（1-2 秒），这是正常行为。跨项目切换时会自动 `cd` 到目标项目目录。

---

## 场景 4：从 Telegram 切换 Project

**目标**：浏览不同项目并选择 session

```
/projects
```

1. 显示项目列表（完整路径，按最近活跃排序）
2. 点击某个项目 → 显示该项目下的 session 列表
3. 点击 session 恢复，或点击 "新建 session"

> 只显示 30 天内活跃、非空、格式正确的 session。

跨项目操作时，Bridge 会自动：
1. 退出当前 Claude
2. `cd` 到目标项目目录
3. 启动 Claude 并恢复/新建 session

---

## 场景 5：从 Telegram 暂停同步

**目标**：暂时停止双向同步（不断开连接）

```
/stop
```

效果：
- Telegram 消息不再转发到桌面
- 桌面的 Claude 回复不再发送到 Telegram
- **日志仍然记录**（`~/.claude/logs/` 中继续写入）
- 桌面 Claude 正常使用不受影响

恢复方法：
```
/start      ← 新建对话并恢复
/resume     ← 选择 session 并恢复
/continue   ← 继续最近 session 并恢复
```

---

## 场景 6：从 Telegram 中断 Claude

**目标**：Claude 正在执行长任务，想打断它

```
/escape
```

等同于在桌面按 `Escape` 键。Claude 会停止当前操作，等待新输入。**同步状态不变**。

> `/escape` vs `/stop`：`/escape` 只中断 Claude 当前操作，同步保持活跃；`/stop` 暂停整个同步通道。

---

## 场景 7：从 Telegram 彻底断开

**目标**：完全停止同步

```
/terminate
```

效果：
- 同步完全停止
- 需要 `/start` 或 `/resume` 才能重连
- 日志仍然记录

---

## 场景 8：从 Telegram 重连

### 新建对话
```
/start
```

### 恢复已有 session
```
/resume
```

### 快速恢复最近 session
```
/continue
```

以上命令都会自动清除暂停/断开状态，恢复同步。

---

## 场景 9：查看状态

```
/status
```

显示信息：
- tmux session 状态（running / not found）
- 同步状态（active / paused / terminated）
- 当前 session ID
- 绑定状态（是否绑定到当前 chat）

---

# 桌面端场景

## 场景 10：首次启动

**目标**：创建 tmux session + 启动 Claude + 启动 Bridge + 连接 Telegram

```bash
# 1. 确保环境变量已设置
echo $TELEGRAM_BOT_TOKEN

# 2. 安装 Hook（首次需要）
./scripts/start.sh --setup-hook

# 3. 创建新 session 并启动所有服务
./scripts/start.sh --new

# 或者指定项目目录
./scripts/start.sh --new ~/Projects/my-app
```

启动后会自动 attach 到 tmux。在 Telegram 发一条消息测试同步。

---

## 场景 11：日常使用（桌面为主）

**目标**：在桌面使用 Claude Code，Telegram 自动接收通知

```bash
# 启动 Bridge（tmux session 已存在）
./scripts/start.sh
```

- 桌面正常使用 Claude Code
- 你的每条输入和 Claude 的回复会自动同步到 Telegram
- 无需在 Telegram 做任何操作

---

## 场景 12：重启 Bridge

**目标**：连接不稳定或消息不同步时

```bash
./scripts/start.sh
```

会自动：
1. 停止旧的 bridge 和 tunnel 进程
2. 启动新的 bridge
3. 创建新的 cloudflared tunnel
4. 设置 Telegram webhook
5. 注册最新的 bot 命令列表

---

## 场景 13：查看 Claude 输出

**目标**：不进入 tmux，快速查看 Claude 最近输出

```bash
./scripts/start.sh --view
```

如果需要进入交互：

```bash
./scripts/start.sh --attach
```

从 tmux 退出（从另一个终端）：

```bash
./scripts/start.sh --detach
```

---

## 场景 14：为不同项目创建 Session

**目标**：在指定项目目录启动新的 Claude session

```bash
./scripts/start.sh --new ~/Projects/another-project
```

tmux session 的工作目录会设为指定路径，Claude 会在该目录启动。

---

## 场景 15：从桌面断开同步

**目标**：暂时停止桌面→Telegram 同步

```bash
./scripts/start.sh --terminate
```

效果同 Telegram `/terminate`，完全停止同步。重启 bridge 即可恢复。

---

## 场景 16：更新 Hook 脚本

**目标**：代码更新后，重新安装 hook

```bash
# 更新 hook 脚本
./scripts/start.sh --setup-hook

# 重启 bridge（注册最新命令）
./scripts/start.sh
```

无需重装整个项目。

---

## 场景 17：完全停止服务

**目标**：停止所有相关进程

```bash
# 方法 1：
./scripts/start.sh --terminate

# 方法 2：在 bridge 终端按 Ctrl+C
```

如果需要，也可以手动清理：

```bash
./scripts/start.sh --detach     # 先脱离 tmux
./scripts/start.sh --terminate  # 终止所有进程
```

---

## 命令速查

完整命令表见 [启动指南](start.md)。

---

## 常见问题

> 安装相关问题见 [安装指南](install.md#常见问题)，连接/日志问题见 [启动指南](start.md#常见问题)。

### Q: 切换 session 后桌面 Claude 断开了？
A: 这是正常行为。从 Telegram 切换 session 时，Claude 会短暂退出并重启（1-2 秒）。Bridge 会自动处理。跨项目切换时会先 `cd` 到目标项目目录再启动。

### Q: 发消息提示 "Not bound"？
A: 发送 `/bind` 绑定当前 session，或者直接再发一条消息（自动绑定）。

### Q: `/stop` 和 `/escape` 有什么区别？
A: `/stop` **暂停整个同步通道**，双向消息都停止，需要 `/start`、`/resume` 或 `/continue` 恢复。`/escape` **只中断 Claude 当前操作**（等于按 Escape），同步保持活跃。

### Q: 切换到其他项目的 session 提示 "session not found"？
A: 使用 `/projects` 浏览项目并选择 session。Bridge 会自动检测跨项目切换并处理 `cd` + 重启。

### Q: Telegram 命令没有更新（看不到新命令）？
A: 重启 Bridge 即可。Bridge 启动时会自动向 Telegram API 注册最新的命令列表。

### Q: 如何更新 bot 命令但不重装？
A: 运行 `./scripts/start.sh --setup-hook` 更新 hook 脚本，然后 `./scripts/start.sh` 重启 bridge 注册新命令。
