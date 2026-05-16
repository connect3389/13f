# 13F · 本地 EDGAR 库

从 SEC 抓取 13F-HR，写入 SQLite，用 Streamlit 浏览持仓、Ticker 与 GICS 行业流向。

- 机构清单：`config/filers_watchlist.yaml`
- 数据库：`data/13f_history.sqlite`
- 原始 XML：`data/raw/<CIK>/`
- 开发原理：[docs/开发原理-证券标识与行业映射.md](docs/开发原理-证券标识与行业映射.md)

---

## 首次运行（一条龙）

在项目根目录依次执行下面各节 **§1 → §2 → §3 → §4 → §5**。日常只需重复 **§3、§4、§5**。

---

## 1. 环境与依赖

```bash
cd /path/to/13f

# 命令行抓取 + 证券主数据（OpenFIGI）
uv sync

# Web 界面 + GICS（yfinance / Streamlit）
uv sync --extra gui

# SEC 必填：可联系邮箱（勿提交 .env）
cp .env.example .env
# 编辑 .env → THIRTEENF_SEC_USER_AGENT='姓名 你的邮箱@example.com'
```

可选环境变量（写入 `.env`）：

| 变量 | 用途 |
|------|------|
| `THIRTEENF_SEC_USER_AGENT` | 访问 SEC EDGAR（**必填**） |
| `OPENFIGI_API_KEY` | OpenFIGI 限流放宽（可选） |
| `THIRTEENF_SEC_DELAY` | SEC 请求间隔秒数（默认约 0.12） |

---

## 2. 初始化：库表 + 证券主数据

**仅第一次**（或新建空库）需要。

### 2.1 建表

```bash
uv run python -m thirteenf.cli --init-db-only
```

等价：`uv run thirteenf-scrape --init-db-only`。

### 2.2 配置机构

编辑 `config/filers_watchlist.yaml`（每行至少 `cik`；`display_name` 建议与 SEC 登记名一致）。  
CIK 可在 [SEC EDGAR Company Search](https://www.sec.gov/edgar/searchedgar/companysearch) 查询（13F 看**管理人法人**，不是基金经理个人名）。

### 2.3 首次抓取 13F

```bash
uv run thirteenf-scrape --max-per-filer 20
```

`--max-per-filer` 与数字之间须有空格。默认每机构最多处理若干条 13F（见 `thirteenf/cli.py`）。

### 2.4 首次证券主数据（全量）

有持仓行之后，按顺序执行（OpenFIGI → Yahoo/GICS）：

```bash
uv run thirteenf-sync-cusip-refs --force-all
uv run thirteenf-sync-gics-sectors --force-all
```

无 `OPENFIGI_API_KEY` 时 CUSIP 同步较慢（约每 10 个 CUSIP 一批）；GICS 全量约数百个 ticker，需数分钟。

---

## 3. 抓取 13F（日常 / 增量）

```bash
cd /path/to/13f

# 按 watchlist 增量抓取（已 complete 且版本一致则跳过）
uv run thirteenf-scrape --max-per-filer 20
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--config` | watchlist 路径（默认 `config/filers_watchlist.yaml`） |
| `--db` | SQLite 路径（默认 `data/13f_history.sqlite`） |
| `--raw-dir` | 原始 XML 目录（默认 `data/raw`） |
| `--max-per-filer N` | 每个机构最多处理 N 条 13F（含跳过计数） |
| `--force` | 强制重拉已是 `complete` 的同一 accession（慎用） |
| `--name-verify` | `auto` / `off` / `warn` / `fail` |

等价入口：`uv run python -m thirteenf.cli …`（参数相同）。

---

## 4. 追加证券主数据（抓取后）

**每次** `thirteenf-scrape` 有新持仓后执行（顺序不可颠倒）：

```bash
# CUSIP → Ticker / 名称（OpenFIGI；先 CUSIP，未命中再 CINS）
uv run thirteenf-sync-cusip-refs --refresh-gaps

# Ticker → GICS 一级～四级（Yahoo + 本地官方层级表）
uv run thirteenf-sync-gics-sectors
```

| 场景 | CUSIP 命令 | GICS 命令 |
|------|------------|-----------|
| **日常（推荐）** | `--refresh-gaps` | 不加参数（只补空缺） |
| 首次 / 映射乱了 | `--force-all` | `--force-all` |
| 仅全新 CUSIP、省 API | 不加参数 | — |

限流示例：

```bash
uv run thirteenf-sync-cusip-refs --refresh-gaps --sleep 1.5
uv run thirteenf-sync-gics-sectors --sleep 0.5
```

---

## 5. 运行 Web

```bash
cd /path/to/13f
uv run streamlit run thirteenf/gui/browse.py
```

浏览器打开终端里的地址（一般为 `http://localhost:8501`）。请在**项目根**启动；侧栏可改数据库路径。

改代码或主数据后：刷新页面；若仍旧数据，在 Streamlit 菜单 **Clear cache** 或重启进程。

---

## 6. 意外情况与排错

### SEC 抓取 403 / 界面突然没有报送

**原因**：未设置或未加载 `THIRTEENF_SEC_USER_AGENT`；用 `--force` 重抓时 SEC 拒绝请求，报送会变成 `failed`，界面只显示 `complete`。

**处理**：

```bash
# 确认 .env 已填写，并在同一终端：
export THIRTEENF_SEC_USER_AGENT='姓名 邮箱@example.com'   # 或 rely on .env

uv run thirteenf-scrape --max-per-filer 20 --force   # 仅当确实要覆盖时用 --force
```

检查：`sqlite3 data/13f_history.sqlite "SELECT status, COUNT(*) FROM ingest_record GROUP BY status;"`

### 抓取成功但 Ticker 全是空 / `NAN` / `(CUSIP)`

**原因**：未跑 CUSIP 同步，或只同步了少量 CUSIP（默认模式不覆盖已有行）。

**处理**：

```bash
uv run thirteenf-sync-cusip-refs --refresh-gaps
# 仍大量空缺时：
uv run thirteenf-sync-cusip-refs --force-all
```

### 「另有 N 个 CUSIP 尚无 GICS 映射」

**原因**：未跑 GICS 同步，或 Yahoo 无行业 / 无 Ticker（债券、误映射 ticker 等）。

**处理**：

```bash
uv run thirteenf-sync-gics-sectors --force-all
```

须先完成 CUSIP→Ticker。界面 caption 统计的是**当前报送**内仍无 `gics_sector_code` 的 CUSIP，属正常缺口。

### OpenFIGI 429 / 同步很慢

**处理**：配置 `OPENFIGI_API_KEY`；加大 `--sleep`；避免频繁 `--force-all`。

### GICS 同步出现 `HTTP Error 404 … symbol: 1B2`

**原因**：OpenFIGI 偶发错映射（如 Bitfarms→`1B2`），Yahoo 无此代码。当前实现会跳过此类 ticker 并抑制 404 刷屏，**不中断**整次同步。

### `--force` 与 `--max-per-filer`

- `--force`：只在你确认要覆盖库中已有 `complete` 记录时使用。  
- `--max-per-filer`：限制每个机构处理条数；SEC `submissions` 仅 `recent` 列表，**更早历史需改代码**（尚未支持 `filings.files` 分页）。  
- 新机构在 EDGAR 上可能只有近几年 13F，不是条数设太小唯一原因。

### `failed` 报送

查看原因：`sqlite3 data/13f_history.sqlite "SELECT report_date, warnings_json FROM ingest_record WHERE status='failed' LIMIT 5;"`  
常见为 403、XML 解析失败、名称校验 `fail`。修正后重新 `thirteenf-scrape`（`failed` 会自动重试）。

### 名称校验

watchlist 的 `display_name` 与 SEC 不一致时，默认 `auto` 可能 `warn` 或 `fail`。可在 `config/filers_watchlist.yaml` 的 `defaults.name_verify` 或 CLI `--name-verify off` 调整。

### 数据与命令对照

| 命令 | 作用 |
|------|------|
| `thirteenf-scrape` | SEC → `ingest_record` + `holding_line` + `data/raw/` |
| `thirteenf-sync-cusip-refs` | `holding_line.cusip` → OpenFIGI → `cusip_ref.ticker` |
| `thirteenf-sync-gics-sectors` | `cusip_ref.ticker` → Yahoo → `cusip_ref.gics_*` |

更细的匹配逻辑与表结构见 [开发原理文档](docs/开发原理-证券标识与行业映射.md)。
