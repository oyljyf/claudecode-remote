# 重构版本新增需求文档（PRD）

- Version: 1.0.4
- Updated at: 2026-02-10 07:46:53
- Status: ✅ Complete

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

### 问题 6: 本地提醒音 — Claude 需要关注时播放警报 ✅

**背景**:
当 Claude 完成任务或需要用户输入时，用户可能不在当前窗口。通过 Claude Code hooks 播放本地声音提醒用户。

**实现方案**: Stop hook + Notification hook（matcher: `permission_prompt|elicitation_dialog`）

```
Claude stops / asks question / requests permission
  → play-alarm.sh → afplay/aplay/paplay (background)
```

**实现细节**: 见 [alarm-hook-plan.md](./spec/alarm-hook-plan.md)

**文件变更**:

| 文件                   | 操作                                  |
| ---------------------- | ------------------------------------- |
| `hooks/play-alarm.sh`  | 新建 — alarm hook 脚本                |
| `sounds/`              | 新建目录 — 预留声音文件位置           |
| `scripts/install.sh`   | 更新 — 复制 alarm hook + sounds       |
| `scripts/start.sh`     | 更新 — `--setup-hook` 注册 alarm hook |
| `scripts/uninstall.sh` | 更新 — 清理 alarm 相关文件            |

**成功标准**:
- ✅ Claude 完成任务/等待输入时播放提醒音（Stop hook）
- ✅ Claude 提问/请求权限时播放提醒音（Notification hook）
- ✅ 不阻塞 hook 执行（后台播放）
- ✅ 无声音文件时静默跳过
- ✅ macOS 和 Linux 都支持

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

---

### 最终目标

1. ✅ 稳定的 Telegram ↔ 桌面双向同步
2. ✅ 用户可手动控制连接状态 (Start/Stop/Terminate)
3. ✅ 可随时选择并重连旧 session
4. ✅ Tmux 滚动功能正常
5. ✅ 完善的卸载功能
6. ✅ Claude 需要关注时本地声音提醒：Stop + Notification hooks（待用户提供 alarm.mp3）
7. ✅ 从 Telegram 远程响应 Claude 的权限请求（PermissionRequest hook）

---

**主要改进**:
- 明确区分了现状、任务和成功标准
- 突出标注了两个关键痛点 (P0)
- 清晰定义了三种连接控制命令的区别
- 添加了可量化的成功标准表格
- 结构更紧凑,减少冗余描述