# Named Tunnel Support Plan

- Version: 1.0.0
- Updated at: 2026-02-22 02:52:09
- Status: 📝 Planning

---

## 背景

当前 `start.sh` 只支持 Cloudflare **Quick Tunnel**（临时隧道），每次启动都会分配一个随机 URL（如 `https://abc-def-ghi.trycloudflare.com`），导致：

| 问题 | 影响 |
|------|------|
| URL 每次变化 | 每次重启都要重新 setWebhook，Telegram Bot 的 webhook URL 频繁更新 |
| 冷启动慢 | 需等待 ~20s URL 生成 + 10s DNS 传播 |
| 无法自定义域名 | 无法用固定域名（如 `claude.example.com`） |

Cloudflare **Named Tunnel**（命名隧道）提供固定 URL，适合生产环境和频繁重启的场景。

---

## 目标

1. **向后兼容**：未配置 Named Tunnel 时，自动降级使用 Quick Tunnel（现有行为不变）
2. **Named Tunnel 支持**：在 `.env` / 环境变量中配置后，自动使用命名隧道
3. **配置示例**：在 `config.env` 中提供注释说明和示例

---

## 设计方案

### 配置项（新增到 `config.env`）

```bash
# Cloudflare Named Tunnel (optional)
# Leave empty to use Quick Tunnel (random URL, no pre-configuration needed)
# To use Named Tunnel:
#   1. Run: cloudflared tunnel create <name>
#   2. Set TUNNEL_NAME to your tunnel name
#   3. Set TUNNEL_HOSTNAME to your custom domain (must be in Cloudflare DNS)
#   4. Configure ~/.cloudflared/config.yml (see below)
#
# Example:
#   DEFAULT_TUNNEL_NAME=claude-remote
#   DEFAULT_TUNNEL_HOSTNAME=claude.example.com
DEFAULT_TUNNEL_NAME=
DEFAULT_TUNNEL_HOSTNAME=
```

### 用户在 shell 中覆盖

```bash
# ~/.zshrc or ~/.bashrc
export TUNNEL_NAME=claude-remote
export TUNNEL_HOSTNAME=claude.example.com
```

### Cloudflare 侧配置（用户一次性操作）

```bash
# 1. 登录 Cloudflare
cloudflared tunnel login

# 2. 创建命名隧道
cloudflared tunnel create claude-remote

# 3. 将自定义域名路由到隧道（DNS CNAME 自动创建）
cloudflared tunnel route dns claude-remote claude.example.com

# 4. 生成 ~/.cloudflared/config.yml
cat > ~/.cloudflared/config.yml << EOF
tunnel: claude-remote
credentials-file: /Users/<username>/.cloudflared/<tunnel-uuid>.json
ingress:
  - hostname: claude.example.com
    service: http://localhost:8080
  - service: http_status:404
EOF
```

---

## start.sh 修改逻辑

### 当前流程（Quick Tunnel Only）

```
cloudflared tunnel --url http://localhost:$PORT &
→ 等待 URL 出现（grep trycloudflare.com）
→ setWebhook
```

### 新流程（条件分支）

```
读取 TUNNEL_NAME / TUNNEL_HOSTNAME 环境变量
  ├── 若 TUNNEL_NAME 非空 → 使用 Named Tunnel
  │     cloudflared tunnel run $TUNNEL_NAME &
  │     TUNNEL_URL=https://$TUNNEL_HOSTNAME
  │     （无需等待 URL，直接 setWebhook）
  │     （无需 DNS 传播等待）
  └── 若为空 → 使用 Quick Tunnel（现有逻辑）
        cloudflared tunnel --url http://localhost:$PORT &
        等待 URL …
        setWebhook
```

### 伪代码

```bash
# In start.sh (tunnel section)
TUNNEL_NAME="${TUNNEL_NAME:-$DEFAULT_TUNNEL_NAME}"
TUNNEL_HOSTNAME="${TUNNEL_HOSTNAME:-$DEFAULT_TUNNEL_HOSTNAME}"

if [ -n "$TUNNEL_NAME" ] && [ -n "$TUNNEL_HOSTNAME" ]; then
    print_info "Starting named tunnel: $TUNNEL_NAME → $TUNNEL_HOSTNAME"
    cloudflared tunnel run "$TUNNEL_NAME" >> "$TUNNEL_LOG" 2>&1 &
    TUNNEL_PID=$!
    TUNNEL_URL="https://$TUNNEL_HOSTNAME"

    # Wait briefly for tunnel to register
    print_info "Waiting for named tunnel to connect..."
    for i in {1..20}; do
        sleep 1
        if ! kill -0 $TUNNEL_PID 2>/dev/null; then
            print_error "Named tunnel process died"
            cat "$TUNNEL_LOG"
            cleanup; exit 1
        fi
        if grep -q "Registered tunnel connection" "$TUNNEL_LOG" 2>/dev/null; then
            break
        fi
        echo -n "."
    done
    echo ""
    print_status "Named tunnel connected: $TUNNEL_URL"
    # Named tunnels don't need DNS propagation wait
else
    print_info "Starting quick tunnel (no TUNNEL_NAME configured)..."
    cloudflared tunnel --url http://localhost:$PORT >> "$TUNNEL_LOG" 2>&1 &
    TUNNEL_PID=$!
    # ... existing URL extraction and DNS wait logic ...
fi
```

---

## config.env 最终样子

```bash
# claudecode-remote defaults
# Shared by bridge.py and scripts/lib/common.sh
# Override via environment variables: export PORT=9090

# Bridge defaults settings
DEFAULT_PORT=8080
DEFAULT_TMUX_SESSION=claude

# Log file name format
DEFAULT_LOG_DATE_FORMAT=%m%d%Y

# Local alarm sound defaults
DEFAULT_SOUND_DIR=~/.claude/sounds
DEFAULT_SOUND_DONE=done.mp3
DEFAULT_SOUND_ALERT=alert.mp3
DEFAULT_ALARM_VOLUME=0.5

# Cloudflare Tunnel (optional Named Tunnel)
# Leave empty to use Quick Tunnel (temporary random URL, no setup needed)
# Set both to use a Named Tunnel (fixed URL, requires one-time Cloudflare setup):
#   Step 1: cloudflared tunnel login
#   Step 2: cloudflared tunnel create <name>
#   Step 3: cloudflared tunnel route dns <name> <hostname>
#   Step 4: Create ~/.cloudflared/config.yml with ingress rules
#
# Example:
#   export TUNNEL_NAME=claude-remote
#   export TUNNEL_HOSTNAME=claude.example.com
DEFAULT_TUNNEL_NAME=
DEFAULT_TUNNEL_HOSTNAME=
```

---

## 影响范围

| 文件 | 修改内容 |
|------|---------|
| `config.env` | 新增 `DEFAULT_TUNNEL_NAME` / `DEFAULT_TUNNEL_HOSTNAME`（默认为空） |
| `scripts/start.sh` | Tunnel 启动段加 `if/else` 分支；Named Tunnel 跳过 DNS 等待 |
| `scripts/lib/common.sh` | 加载新变量（若 common.sh 有 source config.env 就自动生效） |
| `README.md` / `README_CN.md` | 新增"Named Tunnel（可选）"配置章节 |
| `docs/usage.md` | 补充 Named Tunnel 使用说明 |
| `tests/` | 新增 `test_named_tunnel` 测试（mock cloudflared 调用） |

---

## 测试计划

| 场景 | 验证点 |
|------|--------|
| `TUNNEL_NAME` 为空 | 走 Quick Tunnel 分支，URL 从日志提取 |
| `TUNNEL_NAME` 已设置，`TUNNEL_HOSTNAME` 已设置 | 走 Named Tunnel 分支，URL = `https://$TUNNEL_HOSTNAME`，无 DNS 等待 |
| Named Tunnel 进程崩溃 | 错误提示正确，清理进程退出 |
| `TUNNEL_NAME` 设置但 `TUNNEL_HOSTNAME` 为空 | 报错提示两者必须同时设置 |

---

## 注意事项

- Named Tunnel 需要用户**提前在 Cloudflare 侧一次性配置**（创建隧道、路由 DNS）
- `credentials-file` 路径含用户名，不能提交到仓库
- Quick Tunnel 仍为默认值，不破坏现有用户的使用习惯
- Named Tunnel 的 `config.yml` 中的 `service: http://localhost:8080` 端口需与 `PORT` 一致；文档应提示用户注意
