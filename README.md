# Kinship Archive

A self-hosted, **relationship-generic** archive: keep the details that matter about the people in your life — a partner, family, friends — in one queryable place, and let it remind you of the days that matter.

> Built because "remembering things about people" is a real job, and a text file stops scaling the moment you have more than one person and more than one type of record.

**All personal data stays on your machine.** The repository contains code only — see [Privacy model](#privacy-model).

## What it does

- **One timeline per person** — text notes, outfits, gifts, meetings, health, milestones; filterable, searchable.
- **Wardrobe (two layers, deduplicated)** — a garment is a **single row** (`wardrobe_items`, unique per person + category + name + color); wearing it again adds a *wear record* (`outfit_wears`) instead of a new event, so "worn 3 times · last seen 10 days ago" is computed, never hand-maintained. A duplicate detector proposes likely repeats (same name, or names that contain each other) and merging is always a human decision — a soft delete that can be undone. Merge `宝蓝色毛衣` with `浅蓝色毛衣` automatically and you have destroyed real information.
- **Photo-records** — attach images to any record (outfit-of-the-day, a gift, a receipt). HEIC from an iPhone is converted server-side. Thumbnails are generated with Pillow (`pillow-heif` for HEIC); images smaller than the thumbnail budget are left alone (never upscaled).
- **Companion module (opt-in per person)** — cycle records, calendar view and a predicted window. *Predictions are a courtesy reminder only (assume ±3 days) and must not be used for contraception or any medical decision.*
- **Time-together tracking** — visits, overnights, days-since-last-meeting.
- **Relationship graph** — who is who to whom (parent, uncle, cousin…).
- **Reminder engine** — birthdays (solar **and** lunar), anniversaries, cycle windows, "no contact for N days", open to-dos; delivered as a daily digest.
- **Per-person modules** — a partner gets the cycle module, a colleague gets birthday + contact log. Same code, different switches.
- **Two entry points** — the web UI, or your chat assistant hitting the same API.

## Privacy model

The app is split so that **code, configuration and data never share a repository**:

| Layer | Location (this deployment) | In git? |
| --- | --- | --- |
| Code | `app/` (repo root) | ✅ public |
| Config + secrets | `deploy/.env`, `deploy/config.toml` | ❌ never |
| Data | MySQL database + `deploy/media/` | ❌ never |

`deploy/` is deliberately **outside the git working tree**, so a stray `git add -f` cannot leak it. On top of that:

1. `.gitignore` blanket-excludes media, databases, `.env*`, images.
2. A dependency-free **pre-commit hook** (`hooks/pre-commit`) blocks private paths and greps staged lines against a keyword denylist that lives *outside* the repository (`$ARCHIVE_DENYLIST`). Absent denylist → the check silently skips, so CI and contributors are unaffected.
3. **gitleaks** runs in CI as a second net.
4. Tests use synthetic fixtures only — a fake person, a generated colour-block image, no real data anywhere.

> Even with all of this, note that publishing this repository discloses *that you run it*. Keep the repo private if that matters to you.

## Stack

- **Frontend** — Vue 3 + Vite + Vue Router + Pinia + [Vant](https://vant-ui.github.io/vant/) (mobile-first) + PWA
- **Backend** — FastAPI + SQLAlchemy 2.0 + Alembic + PyMySQL
- **Database** — MySQL 8.4 or MariaDB 11.x (utf8mb4). Search is plain `LIKE`, deliberately without any full-text parser — the `ngram` parser exists only on MySQL, so a schema that depends on it cannot even migrate to MariaDB.
- **Images** — Pillow + `pillow-heif` for resize and HEIC conversion (cross-platform; no macOS-only `sips`).
- **Lunar calendar** — self-contained 1900–2099 converter (no third-party dependency)

## Quickstart (development)

```bash
# 0. prerequisites: MySQL 8.4 running, Python 3.9+, Node 20+
brew install mysql@8.4 && brew services start mysql@8.4

# 1. clone & configure
git clone <this-repo> app && cd app
mkdir -p ../deploy/media ../deploy/backups ../deploy/logs
cp config.example.toml ../deploy/config.toml
cp .env.example ../deploy/.env        # then fill in DB credentials / UI token

# 2. database
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
alembic upgrade head

# 3. backend
uvicorn backend.main:app --reload --port 8787

# 4. frontend (separate shell)
cd frontend && npm install && npm run dev -- --host
```

Production: `npm run build` into `../deploy/dist/`, then run uvicorn on `8787` and open
`http://<lan-ip>:8787`. launchd templates live in `ops/launchd/` (rendered to
`~/Library/LaunchAgents/` by `ops/install-launchd.sh`, so no absolute path is ever
committed).

## 运行方式

```bash
bash ops/serve.sh start     # 后台启动（写 pidfile）
bash ops/serve.sh status    # 探活（直接打 /api/health）
bash ops/serve.sh stop
bash ops/serve.sh ensure    # 没跑就启动（给调度器/守护用）
```

**⚠️ 不要把服务挂到 launchd / LaunchAgent 上，除非仓库不在受保护目录。** macOS 的 TCC
保护 `~/Desktop`、`~/Documents`、`~/Downloads`：launchd 拉起的进程读不到放在这些目录里的
代码和 venv，实测报 `Operation not permitted`，Python 会**卡死在解释器启动阶段**（无任何日志，
极难排查）。三条出路，任选其一：

1. 把仓库放到非受保护目录（如 `~/projects/`）；
2. 给运行它的解释器授予「完全磁盘访问权限」（系统设置 → 隐私与安全性）；
3. 用有权限的上下文做守护 —— 本机做法：`ops/serve.sh ensure` 交给一个每 5 分钟的定时任务，
   脚本只写 pid 与日志，不依赖 cwd（用 `BASH_SOURCE` 定位仓库根）。

## Data model (short version)

`persons` (including **you**, `is_self`) · `person_relations` (edges) · `person_modules` (per-person feature switches) · `attributes` (per-person key/value + category) · `events` + `event_persons` (unified timeline, multi-person events) · `event_types` · `wardrobe_items` (one row per garment, unique per person+category+name+color, `merged_into_id` for reversible de-duplication) · `outfit_wears` (outfit event ↔ garment; wear counts and last-worn are aggregated, never stored twice) · `cycle_records` · `interactions` · `gifts` (giver → receiver) · `special_days` (lunar-aware) · `todos` · `media` (polymorphic: person / event / garment) · `sensitivity`-masked fields.

## Repository layout

```
app/            # this repository (public, code only)
frontend/       # Vue SPA
backend/        # FastAPI app, models, Alembic migrations
migrate/        # generic Markdown → database importer
hooks/          # pre-commit privacy guard
tests/          # synthetic fixtures only
../deploy/      # runtime: dist/, media/, backups/, .env, logs/  (NOT in git)
```

## Roadmap

- [x] P0 — environment (MySQL 8.4), repository skeleton, privacy guards, CI
- [x] P1 — schema + Alembic, person switcher, module switches, four record types, timeline,
  today card (lunar countdown), cycle prediction, search, to-do pool
- [x] P2 — image/video upload (HEIC auto-convert, Pillow thumbnails), gallery, to-do pool, dashboard
- [x] P2.5 — wardrobe rework: garments as first-class records (`wardrobe_items` + `outfit_wears`),
  duplicate candidates with human-confirmed, reversible merging; outfit entry by picking garments
- [ ] P3 — cycle calendar, together-stats, relationship graph, PWA, daily digest

## License

MIT — see `LICENSE`.
