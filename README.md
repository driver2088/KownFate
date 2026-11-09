# 知天命 · 早知命早改命

AI 八字命理网站：排盘 → 五行十神强弱喜用（扶抑为主、调候互参）→ 命格校验（5 题算准 4 题定案；未过由 AI 复核定稿，最多三轮；三轮不达则不存档）→ 存档 → AI 大事答疑（每次 3 轮，流式输出）。

UI 走现代简约风：Manrope + Noto Serif SC 思源宋体（标题字族与知命书院对齐）、细线与留白、单一朱砂点缀。注册登录面向海外用户，以邮箱为账号（登录/注册为按需弹窗，首页左文案右罗盘）。推算门派策略（扶抑/调候等）仅存于内部字段与 AI 上下文，页面不展示。

## 启动

```bash
cd /Users/Admin/Dev/KownFate
./run.sh            # 首次运行会自动创建虚拟环境并安装依赖
# 打开 http://127.0.0.1:8000
```

> 注意：用户表已从 username 迁移为 email，旧的本地 `data/kownfate.db` 需删除重建（`rm data/kownfate.db` 后重启）。

## AI 配置（.env）

```
ANTHROPIC_API_KEY=<你的密钥>          # 必需：AI 复核与答疑；缺省时校验自动回退流派重排
ANTHROPIC_BASE_URL=<可选>             # Anthropic 官方或任意 anthropic 兼容端点
KOWNFATE_MODEL=<可选>                 # 模型名（默认 claude-opus-5-5）
```

> `.env` 中的配置会覆盖 shell 环境变量（`load_dotenv(override=True)`），
> 避免与本机 Claude Code 自身的全局代理配置互相干扰。
> 推理型端点会先消耗 thinking token，AI 复核请求 max_tokens 已预留 8000。

## 功能与算法说明

| 模块 | 实现 |
|---|---|
| 注册登录 | **邮箱** + 密码（昵称可选，默认取邮箱前缀；大小写不敏感），bcrypt 散列，JWT（72h），密钥存 `data/.jwt_secret` |
| 历法录入 | 出生日期支持**公历 / 农历**（含闰月勾选）；农历经 `lunar-python` 换算公历并回转校验（闰月存在性、月末天数越界均给出中文报错，如"农历1990年六月只有 29 天，无30日"），同一生日两种历法起盘四柱全等，转换说明写入命盘并在命盘页展示 |
| 排盘 | `lunar-python` 节气定月柱、`getEightChar` 四柱；按出生地经度 + 均时差校正**真太阳时**（120+ 城市，未计夏令时，属近似） |
| 五行/十神 | 藏干本中余气表、十神推导表；十神按柱位加权（月支 36 · 日支 14 · 时支 13 · 年支 13 · 干各 8） |
| 强弱 | 生扶力量占比 ≥55% 身强、≤45% 身弱，其间中和 |
| 喜用神 | **扶抑派**取用（身强取克泄耗之有力者、身弱取印比），并列给出**调候参考**（月令寒暖燥湿粗取，细论依穷通宝鉴）；两者一并写入命格摘要 |
| 大运流年 | `getYun` 起运 + 大运盘；流年按喜忌打分，叠加日支/月支六冲、咸池桃花；另取成年后近 25 个流年备应期校验 |
| 命格校验 | 5 道判断题：**1 性格、2 事业或感情（择命局主导之星）、3-5 关键大运/流年应期**；**算准 ≥4 题即定案**。未通过时：①优先将校验结果连同命盘交 AI 依子平复核，**推演主旨逐轮递变——一轮扶抑为主（定式排盘）、二轮调候为主（宗穷通宝鉴）、三轮综合两派就命主反馈折衡定盘**，重判强弱喜用后 `rescore` 岁运并重拟题面（本轮主旨仅存内部字段 `xiyong.school` / `variant.focus`，面向用户的轮次说明保持中性）；②AI 不可用则回退推算方法重排（钟表时间 → 子时早晚 → 强弱重判另取喜用）。**三轮打磨仍未达标 → 本次不定案、不存档**，退回排盘表单并提醒核对出生日期/时辰/地点，修正重提后另起新链条。各轮校验反馈随命盘归档 |
| AI 答疑 | 定案命格（含扶抑/调候取用依据与历轮校验反馈）注入 system prompt，并明示"门派策略只作立论根基，答语勿向命主复述扶抑/调候等门径术语，直断用神与应期"；每次咨询限 3 轮（服务端强校验，失败不占轮次）；**SSE 流式输出**；对话全文存档 |
| 存档 | 每轮原局、校验答案、算准数、重拟方式与最终状态（confirmed / rejected / **failed 未定案**）全量归档；答疑记录可回看 |

## 目录结构

```
backend/          FastAPI 应用
  ai.py           Anthropic 客户端工厂（复核与答疑共用）
  bazi/           tables(干支五行十神表) engine(排盘 · rescore · AI改判回填)
                  interpret(断语/校验题/命格摘要) recalibrate(AI复核 JSON 契约)
  routers/        auth(邮箱账号) / chart(校验闭环) / chat(SSE 流式答疑)
  cities.py · security.py · database.py(SQLite) · config.py
frontend/         原生 SPA：index.html + css/style.css + js/app.js
data/             kownfate.db · jwt_secret（自动生成，不入库）
```

## API 一览

`POST /api/auth/register|login` · `GET /api/auth/me` · `POST /api/chart/start` ·
`POST /api/chart/{id}/feedback` · `GET /api/chart/current|archive|{id}` ·
`POST /api/chat/send` · `POST /api/chat/stream`（SSE 事件：meta/delta/done/error）·
`GET /api/chat/conversations[/{id}]` · `GET /api/health|cities`

## 免责

算法为传统子平命理的**简化工程实现**，断语由规则与 AI 生成，仅供文化参考与娱乐。
