# 重构版本新增需求文档（PRD）

- Version: 1.0.6
- Updated at: 2026-02-11 08:39:05
- Status: ✅ All Complete

---

## 项目优化需求 - Telegram ↔ 桌面双向同步系统

**修复范围**: Python 代码、start.sh、hooks  
**不修改**: install 逻辑

---

### 问题 1: Session Management 双向同步不对称

**现状**:
- ✅ 桌面 → Telegram 同步稳定 (关闭窗口重开也能基于旧连接继续同步)
- ❌ Telegram → 桌面同步必须每次开启新 tmux session 才能工作
- 新增了 project 选择功能,但无法灵活切换回旧 session

**任务**:
1. 检查 git 历史中 session 处理的各个版本,定位设计问题
2. 诊断 Telegram → 桌面同步失败的根本原因:
   - 设计缺陷 → 提供最优解并修复
   - tmux 限制 → 记录并忽略
3. **必须修复**: tmux 窗口无法滚动查看历史记录 (关键痛点)

---

### 问题 2: Session + Project 双概念架构重构

**设计目标**:
- Session 和 Project 两个概念独立,互不冲突
- 支持对话中途跨 Project 切换 Session,保持流畅体验
- Session 切换丝滑,Project 选择准确

**功能要求**:

**1. 双向同步 (核心)**:
   - 桌面 → Telegram ✓
   - Telegram → 桌面 ✓
   - 两个方向同时正常工作

**2. Session 持久化与恢复**:
   - 误操作退出后可重新连接到原 session
   - 保留 session 历史记录
   - 支持恢复一定时间内的旧 session
   - **原则**: 除非用户主动断开,否则不应强制 "Start New"

**3. 连接控制命令**:
   - `Start New`: 开启新 session (可恢复之前的记录和历史)
   - `Stop`: 暂停双向连接 (不断开,可恢复)
   - `Terminate`: 彻底断开两端连接,停止所有同步

**可重构内容**: 
- 整个 Session + Project 逻辑和流程
- Session 连接方式必须重构

---

### 问题 3: Log 系统持久化

**要求**:
- Log 系统独立于同步状态,始终记录
- 即使执行 `Terminate` 停止同步,Log 仍应继续工作
- **最低保证**: Terminate 前的所有双端对话记录必须完整保存

**优先级**: Session 修复后再处理此模块

---

### 问题 4: Tmux 滚动卡死问题 ⚠️ 高优先级痛点

**现象**:
- Start New 时出现绿色状态栏 (可接受)
- 屏幕滚动功能失效,无法向上查看历史 (不可接受)

**任务**:
- 诊断是 tmux 配置问题还是 tmux bug
- **必须彻底修复**,这是严重影响用户体验的痛点

---

### 问题 5: Uninstall 功能

**需求**:
- 测试现有卸载功能
- 优化卸载流程,确保完整清理:
  - Python 依赖
  - 配置文件和目录
  - Git hooks
  - Tmux sessions
  - Log 文件 (可选保留)
  - 后台进程

---

### 问题 6: 本地提醒音 — 双声音系统 ✅

**功能**: Claude 完成任务/需要操作时播放不同声音提醒

**双声音设计**:

| 场景     | 声音文件    | Hook 事件    | 触发时机             |
| -------- | ----------- | ------------ | -------------------- |
| 任务完成 | `done.mp3`  | Stop         | Claude 完成任务      |
| 需要操作 | `alert.mp3` | Notification | Claude 提问/请求权限 |

**核心配置** (`config.env`):
```bash
DEFAULT_SOUND_DIR=~/.claude/sounds
DEFAULT_SOUND_DONE=done.mp3
DEFAULT_SOUND_ALERT=alert.mp3
DEFAULT_ALARM_VOLUME=0.5
```

**去重机制**: 
- Stop hook 触发时播放 `done.mp3`
- Notification hook 触发时播放 `alert.mp3`
- **不会重复**: 同一事件只触发对应的一个 hook，通过 hook 事件类型天然去重

**成功标准**:
- ✅ 任务完成播放 `done.mp3`，需要操作播放 `alert.mp3`
- ✅ 同一事件不会播放多个声音
- ✅ 后台播放不阻塞
- ✅ 无声音文件时静默跳过
- ✅ 支持 macOS/Linux

**详细设计**: 见 [alarm-hook-plan.md](./spec/alarm-hook-plan.md)

---

### 问题 7: Telegram 远程响应 Claude 权限请求 ✅

**背景**:
当 Claude Code 需要工具权限时（PermissionRequest），用户必须回到桌面终端操作。本功能通过 PermissionRequest hook 将权限请求转发到 Telegram，用户点击 Allow/Deny 按钮即可远程响应。

**前提**: 仅在 Claude 不使用 `--dangerously-skip-permissions` 时生效。

**实现方案**: PermissionRequest hook + 文件 IPC + Bridge callback

```
Claude → PermissionRequest hook → Telegram (inline keyboard)
                ↕ (file IPC)
         Bridge ← Telegram callback → permission_response.json
```

**实现细节**: 见 [permission-request-plan.md](./spec/permission-request-plan.md)

**文件变更**:

| 文件                         | 操作                                                                    |
| ---------------------------- | ----------------------------------------------------------------------- |
| `hooks/handle-permission.sh` | 新建 — PermissionRequest hook 脚本                                      |
| `bridge.py`                  | 新增权限回调处理（`CB_PERM_ALLOW/DENY`、`_handle_permission_response`） |
| `hooks/lib/common.sh`        | 新增 `PERM_PENDING_FILE`、`PERM_RESPONSE_FILE`                          |
| `scripts/lib/common.sh`      | 同步新增变量                                                            |
| `scripts/start.sh`           | HOOK_CONFIG + setup_hook() 更新                                         |
| `scripts/install.sh`         | 复制脚本 + jq merge + heredoc                                           |
| `scripts/uninstall.sh`       | state_files + 删除脚本 + jq 清理                                        |

**成功标准**:
- ✅ 权限请求转发到 Telegram 显示 Allow/Deny 按钮
- ✅ 用户点击后 Claude 继续/拒绝执行
- ✅ 120 秒超时自动回退到终端对话框
- ✅ 不影响桌面端正常交互
- ✅ 16 个新增测试全部通过

---

### 问题 8: 本地停止同步机制（不依赖 Bridge） ✅

**背景**:
Hook 直接调用 Telegram API 不经过 bridge，但 `/stop`/`/terminate` 命令由 bridge 处理创建 flag 文件。Bridge 挂掉后用户在 Telegram 发命令无法被处理，hook 继续发送。

**方案**: 在 `start.sh` 添加 `--stop-sync` 和 `--resume-sync` 选项，直接操作 flag 文件：
- `--stop-sync`: 创建 `~/.claude/telegram_sync_paused`，清除 pending 文件
- `--resume-sync`: 删除 `telegram_sync_paused` 和 `telegram_sync_disabled`

**成功标准**:
- ✅ `--stop-sync` 创建 paused flag 文件
- ✅ `--resume-sync` 清除两个 flag 文件
- ✅ 不依赖 bridge 运行
- ✅ 帮助文本和文档已更新

---

### 问题 9: CC 交互对话转发到 Telegram ✅

**背景**: PermissionRequest 和 AskUserQuestion 走不同的 hook 事件路径，需要分别处理。

**实现方案（双 hook 协作）**:

| Hook                               | 事件                                | 职责                                                      |
| ---------------------------------- | ----------------------------------- | --------------------------------------------------------- |
| `handle-permission.sh`             | PermissionRequest                   | 发送工具信息（Bash 命令、Edit 文件等）                    |
| `send-notification-to-telegram.sh` | Notification (`elicitation_dialog`) | 读 transcript 提取 AskUserQuestion 选项 → inline keyboard |

**事件流**:
```
PermissionRequest (Bash/Edit/Write):
  → handle-permission.sh 发工具信息到 TG → exit 0 → CC 显示终端 y/n/a
  → 用户在 TG 回复 → bridge 发到 tmux

AskUserQuestion:
  → CC 自动允许（不走 PermissionRequest）→ Notification (elicitation_dialog) 触发
  → send-notification-to-telegram.sh 读 transcript → 提取选项 → 发 inline keyboard (askq:)
  → 用户点按钮 → bridge Down+Enter 导航 CC TUI
```

**成功标准**:
- ✅ handle-permission.sh 发工具信息（jq 提取，无 AskUserQuestion 死代码）
- ✅ send-notification-to-telegram.sh 读 transcript 提取 AskUserQuestion 选项
- ✅ bridge.py 清理死代码（CB_PERM、PERM_PENDING_FILE、PERM_RESPONSE_FILE）
- ✅ /escape 能中断 permission dialog（Escape + Ctrl+C）

---

### 问题 10: /report Token 用量报告 ✅

**背景**:
用户希望从 Telegram 快速查看 token 使用统计，类似 Claude Code 的 `/insights`。

**方案**: 扫描 `~/.claude/projects/{encoded_project_path}/{session_id}.jsonl`，只解析 `type: "assistant"` 中的 `message.usage` 字段。

**输出格式**:
- 总量：today（含 vs yesterday 趋势 ↑/↓/→）/ 7d / 30d（input + output）
- 今日预估成本（Opus $15/$75, Sonnet $3/$15, Haiku $0.25/$1.25 per 1M tokens）
- Cache：today 的 read + write + 命中率百分比
- By Model (today) + 百分比条 ████░░ + 单模型成本
- By Project (today) + 百分比条
- By Session (today, top 3) + 所属项目名

**关键设计决策**:
- 单次扫描产出所有时间范围（today/yesterday/7d/30d）的数据
- mtime 预过滤跳过超过 31 天的文件
- 快速行预检 `'"usage"' not in line` 跳过 JSON 解析
- "今天"使用本地时区（非 UTC）
- by_model 存储 input/output 分拆，用于精确成本估算
- session_project 映射显示 session 所属项目
- 成本估算基于公开价格表，标注 `~$` 提示为估计值
- session 只显示 top 3 + 8 字符短 UUID + 项目名
- 百分比条宽度 6 字符，填充 █ 和空白 ░

**成功标准**:
- ✅ 44 测试覆盖扫描、格式化、辅助函数
- ✅ Telegram 发送 `/report` 显示正确格式的用量报告
- ✅ 出现在 bot menu 中

**详细设计**: 见 [report-plan.md](./spec/report-plan.md)

---

### 优先级与关键指标

| 优先级 | 任务               | 成功标准                            | 状态 |
| ------ | ------------------ | ----------------------------------- | ---- |
| **P0** | Tmux 滚动修复      | 用户可正常滚动查看历史              | ✅    |
| **P0** | 双向同步稳定性     | Telegram ↔ 桌面同时工作             | ✅    |
| **P1** | Session 恢复机制   | 可随时重连旧 session                | ✅    |
| **P1** | Log 系统持久化     | Terminate 后仍能记录                | ✅    |
| **P2** | Project 切换优化   | 跨 Project 无缝切换                 | ✅    |
| **P2** | Uninstall 测试优化 | 完整清理所有资源                    | ✅    |
| **P1** | 本地提醒音         | Claude 停止/提问/请求权限时播放警报 | ✅    |
| **P1** | Telegram 权限请求  | 从 Telegram 响应 Claude 的权限请求  | ✅    |
| **P1** | 本地停止同步       | 不依赖 bridge 即可暂停/恢复同步     | ✅    |
| **P2** | CC 交互对话转发    | AskUserQuestion → inline keyboard   | ✅    |
| **P2** | /report 用量报告   | 从 Telegram 查看 token 使用统计     | ✅    |

---

### 最终目标

1. ✅ 稳定的 Telegram ↔ 桌面双向同步
2. ✅ 用户可手动控制连接状态 (Start/Stop/Terminate)
3. ✅ 可随时选择并重连旧 session
4. ✅ Tmux 滚动功能正常
5. ✅ 完善的卸载功能
6. ✅ Claude 需要关注时本地双声音提醒：`done.mp3`（任务完成）+ `alert.mp3`（需要操作），配置集中在 config.env
7. ✅ 从 Telegram 远程响应 Claude 的权限请求（PermissionRequest hook）
8. ✅ 本地停止同步机制（`--stop-sync` / `--resume-sync`，不依赖 bridge）
9. ✅ CC 交互对话转发（PermissionRequest → 工具信息，AskUserQuestion → 读 transcript → inline keyboard）
10. ✅ /report 命令查看 token 用量报告（成本估算、趋势对比、百分比条、缓存命中率、session 含项目名）

---

**主要改进**:
- 明确区分了现状、任务和成功标准
- 突出标注了两个关键痛点 (P0)
- 清晰定义了三种连接控制命令的区别
- 添加了可量化的成功标准表格
- 消除了所有 raw JSON 格式泄露（改为 key-value 格式）