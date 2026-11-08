# 知天命 · 早知命早改命

AI 八字命理网站：排盘 → 五行十神强弱喜用 → 命格校验（最多三轮重算）→ 定案存档 → AI 大事答疑（每次 3 轮）。
UI 参考 openfate.ai 的浅色典雅风：宣纸底、墨色衬线、金缕边框、朱砂印章、四柱命盘表格。

## 启动

```bash
cd /Users/Admin/Dev/KownFate
./run.sh            # 首次运行会自动创建虚拟环境并安装依赖
# 打开 http://127.0.0.1:8000
```

已在运行的话（当前即如此）直接访问上述地址。

## AI 答疑配置（.env）

```
ANTHROPIC_API_KEY=<你的密钥>          # 必需：AI 答疑用；缺省时排盘/校验功能不受影响
ANTHROPIC_BASE_URL=<可选>             # Anthropic 官方或任意 anthropic 兼容端点
KOWNFATE_MODEL=<可选>                 # 对话模型名（默认 claude-opus-5-5）
```

> `.env` 中的配置会覆盖 shell 环境变量（`load_dotenv(override=True)`），
> 避免与本机 Claude Code 自身的全局代理配置互相干扰。

## 功能与算法说明

| 模块 | 实现 |
|---|---|
| 登录注册 | 用户名+密码，bcrypt 散列，JWT（72h），密钥存 `data/.jwt_secret` |
| 排盘 | `lunar-python` 节气定月柱、`getEightChar` 四柱；按出生地经度 + 均时差校正**真太阳时**（120+ 城市，未计夏令时，属近似） |
| 五行/十神 | 藏干本中余气表、十神推导表（阴阳生克），十神按柱位加权（月支 36 · 日支 14 · 时支 13 · 年支 13 · 干各 8） |
| 强弱 | 生扶力量占比 ≥55% 身强、≤45% 身弱，其间中和（简化流派，供校验环节纠偏） |
| 喜用神 | 身强取克泄耗（官杀/财/食伤）中力量最大者为用，克泄耗中生化用神者为喜，忌印比；身弱反之，取印比为用 |
| 大运流年 | `getYun` 起运 + 大运盘；十年流年以喜忌打分，叠加日支/月支六冲、咸池桃花判关键词 |
| 命格校验 | 由命盘自动生成 5 道判断题（性格×2、事业、感情、应期）；否定率 >50% 即重算：**R2 改钟表时间重排 → R3 早子时换日重排（若四柱仍不变则换取用方法）**，最多三轮，第三轮无论结果强制定案 |
| AI 答疑 | 定案命格摘要注入 system prompt；每次咨询限 3 轮（服务端强校验）；对话全文存档 |
| 存档 | 排盘记录（每轮原局、校验答案、否定率、状态）+ 咨询记录可回看 |

## 目录结构

```
backend/          FastAPI 应用
  bazi/           tables(干支五行十神表) engine(排盘) interpret(断语+校验题)
  routers/        auth / chart(排盘校验流) chat(AI答疑)
  cities.py       出生地经纬度 · security.py · database.py(SQLite) · config.py
frontend/         原生 SPA：index.html + css/style.css + js/app.js
data/             kownfate.db · jwt_secret（自动生成）
```

## API 一览

`POST /api/auth/register|login` · `GET /api/auth/me` · `POST /api/chart/start` ·
`POST /api/chart/{id}/feedback` · `GET /api/chart/current|archive|{id}` ·
`POST /api/chat/send` · `GET /api/chat/conversations[/{id}]` · `GET /api/health|cities`

## 免责

算法为传统子平命理的**简化工程实现**，断语由规则与 AI 生成，仅供文化参考与娱乐。
