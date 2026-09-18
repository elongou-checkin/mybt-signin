# mybt-signin

纸鸢下载（[mybt.kiteyuan.info](https://mybt.kiteyuan.info)）自动签到脚本，支持：

- Casdoor 账号密码自动登录并刷新 token
- 每日签到
- 访问任务
- GitHub Actions 定时运行

> **声明**：本项目仅供学习交流。使用前请自行确认目标站点服务条款；账号与密码请只放在 GitHub Secrets / 本地环境变量中，切勿写入代码或提交到仓库。此脚本只方便个人签到，请支持网站作者，因此不会支持多账号薅羊毛行为

## 功能

| 能力 | 说明 |
|------|------|
| 自动登录 | 用 Casdoor 用户名/密码换取站点 JWT |
| 签到 | `POST /api/auth/points/tasks/signin` |
| 访问任务 | `POST /api/auth/points/tasks/visit` |
| 签名请求 | 自动生成 `X-Sign` / `X-Timestamp` |
| 结果通知 | 签到结果推送到 WxPusher / PushPlus / 微信测试号（配置了才启用） |

## 快速开始（GitHub Actions）

### 1. Fork 或克隆本仓库

建议先 **Fork** 到自己的账号，再启用 Actions。

### 2. 配置 Secrets

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | 必填 | 说明 |
|------|------|------|
| `MYBT_USERNAME` | 是 | Casdoor 用户名或邮箱 |
| `MYBT_PASSWORD` | 是 | Casdoor 密码 |

可选（兼容/兜底）：

| Name | 说明 |
|------|------|
| `MYBT_TOKEN` | 手动 JWT；自动登录失败时回退 |
| `MYBT_USER_ID` | 用户 id（一般可自动解析） |
| `MYBT_COOKIE` | 如 `cf_clearance=...` |
| `MYBT_TURNSTILE_TOKEN` | 若触发人机验证时可手动提供 |

可选（通知渠道，配置了才启用）：

| Name | 说明 |
|------|------|
| `WXPUSHER_APP_TOKEN` | WxPusher AppToken（AT_ 开头），推荐，免实名免费 |
| `WXPUSHER_UIDS` | WxPusher 用户 UID（UID_ 开头）；多个用英文逗号分隔 |
| `PUSHPLUS_TOKEN` | PushPlus token，需实名认证后方可发送 |
| `WX_TEST_APPID` / `WX_TEST_APP_SECRET` / `WX_TEST_TEMPLATE_ID` / `WX_TEST_OPENID` | 微信公众平台测试号模板消息 |

### 结果通知

脚本结束后会推送签到结果（成功/失败、积分变化）。通知按以下优先级依次尝试，命中第一个可用渠道即停止：

1. **微信测试号**（配置 4 个 `WX_TEST_*` secrets 时启用）：消息在微信「服务通知」中，标题固定，详情需点开查看
2. **WxPusher**（推荐）：免费、免实名，消息内容在 WxPusher App 内直接可见。配置步骤：
   1. 登录 [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com) → 应用管理 → 创建应用，复制 `APP_TOKEN`
   2. 在 WxPusher App 中关注该应用
   3. 配置 secrets：`WXPUSHER_APP_TOKEN` 与 `WXPUSHER_UIDS`（UID 可通过接口 `GET /api/fun/wxuser/v2?appToken=AT_xxx&page=1&pageSize=100` 查询）
3. **PushPlus**：需在 [verify.pushplus.plus](https://verify.pushplus.plus) 完成实名认证，否则返回 code 905

都不配置时不发送通知，不影响签到本身；但日志会输出 `⚠️ 未配置任何可用通知渠道` 告警，
以免「通知配置失效」被误认为一切正常。

### 3. 启用 Actions

1. 打开 **Actions** 页，允许 workflow 运行
2. 选择 `mybt-signin` → **Run workflow**
3. 查看日志，成功示例：

```text
==> 尝试 Casdoor 自动登录续期
✅ 自动登录成功，已获取新 token
signin: 今日已签到
visit: 今日已领取
DONE: success
```

### 4. 定时规则

默认每天运行两次：

- **18:00 UTC**（北京时间次日 **02:00**）
- **01:30 UTC**（北京时间 **09:30**）

可在 `.github/workflows/mybt-signin.yml` 中修改 cron。

## 本地运行

```bash
# 1. 克隆
git clone https://github.com/<your-username>/mybt-signin.git
cd mybt-signin

# 2. 配置环境变量（PowerShell 示例）
$env:MYBT_USERNAME="你的邮箱或用户名"
$env:MYBT_PASSWORD="你的密码"

# 3. 运行
python signin.py
```

也可复制 `.env.example` 为 `.env` 后自行加载（请勿提交 `.env`）。

## 项目结构

```text
mybt-signin/
├── signin.py                         # 主脚本
├── .github/workflows/mybt-signin.yml # Actions 工作流
├── .env.example                      # 环境变量示例
├── .gitignore
├── LICENSE
└── README.md
```

## 工作原理（简述）

1. 访问站点 Casdoor 登录入口，拿到 OAuth `authorize` 参数
2. 向 `auth.kiteyuan.info` 提交账号密码登录，获取 `code`
3. 走 callback 换取站点 JWT
4. 用 JWT + 签名头调用签到/访问接口

## 已知限制

- 登录页可能启用 **Cloudflare Turnstile**。多数情况下账号密码可直接登录；若 Actions 日志出现 `login requires captcha/turnstile`，说明被验证码拦截，需要临时使用 `MYBT_TOKEN` 兜底，或改为本机运行。
- 站点接口或签名算法若变更，脚本可能失效，需要同步更新。
- GitHub Actions 的 `schedule` 可能有延迟，属平台正常现象。


## 免责声明

- 本项目与纸鸢下载 / KiteYuan 官方无关
- 因滥用、封号、积分异常等造成的后果由使用者自行承担
- 请合理设置运行频率，不要对目标站点造成压力

## License

MIT
