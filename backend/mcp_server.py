"""kinship-archive 的 MCP server（stdio）。

把归档服务暴露成 MCP 工具，任何 MCP 客户端（Hermes / Claude Desktop / 别的 agent）
都能直接查人物、关系和记录，不用手拼 HTTP 请求。

设计要点
- **只做 API 包装**：校验、审计、权限都在服务端（backend/main.py + routers/），
  这里绝不直连数据库 —— 免得绕过校验写出脏数据。
- **stdio 传输**：由客户端拉起本地进程，不开端口、不进公网。
- **写工具默认开启**，可用 KINSHIP_MCP_WRITE=0 关掉变只读。
- **不提供删除工具**：删除是有后果的操作，只在网页上做（那边有确认框）。
- 口令从环境或文件读，不打印、不进对话。

启动（一般由 MCP 客户端自动拉起）：
    python -m backend.mcp_server

环境变量：
    KINSHIP_ARCHIVE_URL   默认 http://127.0.0.1:8787
    KINSHIP_ARCHIVE_TOKEN 应用口令（不设则按下面的顺序找文件）
    KINSHIP_ARCHIVE_ENV   指定 .env 文件路径
    KINSHIP_MCP_WRITE     0 = 只读模式
    KINSHIP_MCP_TIMEOUT   单次 API 超时秒数，默认 20
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    # mcp 1.x：FastMCP
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:
    try:
        # mcp 2.x：FastMCP 改名为 MCPServer（API 相同：@server.tool() + run()）
        from mcp.server.mcpserver import MCPServer as _Server
    except ImportError:  # pragma: no cover - 环境没装时给出人话提示
        sys.stderr.write("缺少 mcp SDK：请先 pip install 'mcp>=1.2'（1.x / 2.x 都支持）\n")
        raise

BASE_URL = os.environ.get("KINSHIP_ARCHIVE_URL", "http://127.0.0.1:8787").rstrip("/")
TIMEOUT = float(os.environ.get("KINSHIP_MCP_TIMEOUT", "20"))
WRITE_ENABLED = os.environ.get("KINSHIP_MCP_WRITE", "1") not in ("0", "false", "False")

# 口令的候选位置：环境变量优先，然后是几个 .env
# （~/Desktop 受 macOS TCC 保护，所以额外留一个 ~/.config 下的副本兜底）
ENV_CANDIDATES = [
    os.environ.get("KINSHIP_ARCHIVE_ENV", ""),
    str(Path.home() / "Desktop/kinship-archive/deploy/.env"),
    str(Path.home() / ".config/kinship-archive/mcp.env"),
]

mcp = _Server("kinship-archive")

# 性别取值 → 中文（跟 /api/config 的 genders 一致；模型看得懂中文更省事）
_GENDER_CN = {"female": "女", "male": "男", "other": "其他"}


# ------------------------------------------------------------------ 基础设施

def _token() -> str:
    tok = os.environ.get("KINSHIP_ARCHIVE_TOKEN")
    if tok:
        return tok.strip()
    for cand in ENV_CANDIDATES:
        if not cand:
            continue
        p = Path(cand)
        try:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ARCHIVE_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val:
                        return val
        except OSError:
            continue
    raise RuntimeError(
        "找不到应用口令：请设置 KINSHIP_ARCHIVE_TOKEN，或把它放在 "
        "~/.config/kinship-archive/mcp.env（ARCHIVE_TOKEN=...）"
    )


def _call(method: str, path: str, body: Optional[Dict[str, Any]] = None,
          params: Optional[Dict[str, Any]] = None) -> Any:
    """调归档服务。错误信息原样抛出（含服务端的 4xx/5xx 说明）。"""
    url = BASE_URL + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Archive-Token", _token())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("%s %s → HTTP %s: %s" % (method, path, e.code, detail))
    except urllib.error.URLError as e:
        raise RuntimeError(
            "连不上归档服务（%s）：%s。服务在跑吗？`bash ops/serve.sh ensure`" % (BASE_URL, e.reason)
        )


def _require_write() -> None:
    if not WRITE_ENABLED:
        raise RuntimeError("当前是只读模式（KINSHIP_MCP_WRITE=0），写操作被拒绝")


def _today() -> str:
    """本机（Asia/Shanghai）今天。所有日期参数都按 YYYY-MM-DD 传。"""
    return dt.date.today().isoformat()


def _when(d: Dict[str, Any]) -> str:
    """记录的时刻文本：只记到日 → '2026-10-12'；有时刻 → '2026-10-12 14:03'。"""
    date = str(d.get("event_date") or "")
    t = d.get("event_time")
    return ("%s %s" % (date, str(t)[:5])) if t else date


def _default_event_time(event_date: Optional[str], event_time: Optional[str]) -> Optional[str]:
    """MCP 的默认口径：没给时间、且（没给日期 = 今天 或 给的就是今天）→ 记此刻；
    显式记到过去/未来某天 → 只记到日。

    ★ 别把「现在几点」塞给 10 月 8 号的记录 —— 那不是发生时刻，是编的。
    """
    if event_time:
        return event_time
    if event_date and str(event_date).strip()[:10] != _today():
        return None
    return dt.datetime.now().strftime("%H:%M:%S")


def _all_persons(include_inactive: bool = False) -> List[Dict[str, Any]]:
    params = {"include_inactive": "true"} if include_inactive else None
    return _call("GET", "/api/persons", params=params) or []


def _resolve(person: Any) -> Dict[str, Any]:
    """把人名/ID 解析成人物对象。

    接受：数字 ID、"我"、display_name 精确匹配、别名（逗号/顿号分隔）精确匹配、
    最后才退到子串包含。匹配不到会把候选人列出来，方便纠正。
    """
    if isinstance(person, int) or (isinstance(person, str) and person.strip().isdigit()):
        pid = int(person)
        for p in _all_persons(include_inactive=True):
            if p["id"] == pid:
                return p
        raise RuntimeError("没有 ID=%d 这个人" % pid)

    needle = str(person or "").strip()
    if not needle:
        raise RuntimeError("请指定人（姓名或 ID）")
    people = _all_persons()
    if needle in ("我", "自己", "本人"):
        for p in people:
            if p.get("is_self"):
                return p
    for p in people:
        if p["display_name"] == needle:
            return p
    for p in people:
        aliases = [a.strip() for a in (p.get("aliases") or "").replace("、", ",").split(",")]
        if needle in [a for a in aliases if a]:
            return p
    loose = [p for p in people if needle in p["display_name"] or p["display_name"] in needle]
    if len(loose) == 1:
        return loose[0]
    names = ", ".join("%s(%d)" % (p["display_name"], p["id"]) for p in people)
    if loose:
        raise RuntimeError("“%s”匹配到多个：%s —— 请用 ID 或更完整的名字"
                           % (needle, ", ".join(p["display_name"] for p in loose)))
    raise RuntimeError("找不到“%s”。现有：%s" % (needle, names))


def _p_card(p: Dict[str, Any]) -> str:
    bits = ["#%d %s" % (p["id"], p["display_name"])]
    if p.get("is_self"):
        bits.append("[本人]")
    bits.append("关系=%s" % p.get("relation_type"))
    bits.append("性别=%s" % _GENDER_CN.get(p.get("gender") or "", "未知"))
    bits.append("圈子=%s" % p.get("circle"))
    bits.append("熟悉度=%s" % p.get("familiarity"))
    if p.get("via_name"):
        bits.append("通过=%s" % p["via_name"])
    if p.get("birthday_text"):
        bits.append("生日=%s" % p["birthday_text"])
    elif p.get("birthday"):
        bits.append("生日=%s" % p["birthday"])
    if p.get("birthday_lunar") and p.get("lunar_month"):
        bits.append("农历=%s月%s日" % (p["lunar_month"], p["lunar_day"]))
    if p.get("birthday_next"):
        bits.append("下次=%s（%s 天后）" % (p["birthday_next"], p.get("birthday_days_left")))
    if p.get("aliases"):
        bits.append("别名=%s" % p["aliases"])
    if p.get("sensitivity") == "sensitive":
        bits.append("🔒敏感")
    if p.get("notes"):
        bits.append("备注=%s" % p["notes"])
    return " ".join(bits)


def _ev_line(e: Dict[str, Any]) -> str:
    parts = ["#%s %s [%s]" % (e["id"], _when(e), e.get("type_key"))]
    if e.get("person_name"):
        parts.append(e["person_name"])
    if e.get("title"):
        parts.append(e["title"])
    if e.get("body"):
        parts.append("— %s" % str(e["body"])[:160])
    if e.get("tags"):
        parts.append("(%s)" % e["tags"])
    if e.get("media"):
        parts.append("[%d 张图]" % len(e["media"]))
    return " ".join(parts)


def _safe(fn):
    """把「可预期的错误」当文本返回，而不是抛成不透明的 tool error。

    MCP 客户端只会把异常渲染成 `Error executing tool X`，模型看不到原因，
    也就没法自我纠正（名字写错、服务没起这类）。所以这类错误一律以文本回给模型。
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RuntimeError as e:
            return "⚠️ %s" % e
    return wrapper


# ------------------------------------------------------------------ 读工具

@mcp.tool()
@_safe
def people(circle: Optional[str] = None, relation_type: Optional[str] = None,
           query: Optional[str] = None) -> str:
    """列出人物（一行一人）。

    circle: self(我这边) / partner(伴侣那边) / shared(共同)，
    relation_type: partner/family/friend/colleague/acquaintance/self 等，
    query: 在名字、别名、备注里做子串匹配。
    """
    rows = _all_persons()
    if circle:
        rows = [p for p in rows if p.get("circle") == circle]
    if relation_type:
        rows = [p for p in rows if p.get("relation_type") == relation_type]
    if query:
        q = query.strip()
        rows = [p for p in rows
                if q in p["display_name"] or q in (p.get("aliases") or "") or q in (p.get("notes") or "")]
    if not rows:
        return "（没有匹配的人）"
    return "\n".join(_p_card(p) for p in rows)


@mcp.tool()
@_safe
def person(who: str) -> str:
    """某个人的档案卡：基本信息 + 启用模块 + 属性 + 最近事件 + 生理期预测。

    who: 姓名（或别名/ID，如 "我"）。
    """
    p = _resolve(who)
    pid = p["id"]
    out = [_p_card(p)]
    try:
        mods = _call("GET", "/api/persons/%d/modules" % pid) or {}
        out.append("模块：%s" % ("、".join(mods.get("enabled") or []) or "（无）"))
    except RuntimeError:
        pass
    attrs = _call("GET", "/api/attributes", params={"person_id": pid}) or []
    if attrs:
        by_cat: Dict[str, List[str]] = {}
        for a in attrs:
            by_cat.setdefault(a["category"], []).append(a["value"])
        out.append("属性：")
        for cat, vals in by_cat.items():
            out.append("  %s：%s" % (cat, "、".join(vals)))
    rels = _call("GET", "/api/relations", params={"person_id": pid}) or []
    if rels:
        out.append("关系：" + "；".join(
            "%s —%s→ %s" % (r["from_name"], r["label"], r["to_name"]) for r in rels))
    ev = _call("GET", "/api/events", params={"person_id": pid, "limit": 10}) or {}
    items = ev.get("items") or []
    if items:
        out.append("最近 %d 条记录：" % len(items))
        out.extend("  " + _ev_line(e) for e in items)
    try:
        pred = _call("GET", "/api/cycle/prediction", params={"person_id": pid})
        if pred:
            out.append("生理期预测：" + json.dumps(pred, ensure_ascii=False))
    except RuntimeError:
        pass  # 没开 cycle 模块的人会报错，属正常
    return "\n".join(out)


@mcp.tool()
@_safe
def timeline(who: Optional[str] = None, type_key: Optional[str] = None,
             date_from: Optional[str] = None, date_to: Optional[str] = None,
             q: Optional[str] = None, limit: int = 20) -> str:
    """按时间倒序列出记录（默认全库，指定 who 只看这个人）。

    type_key: text/outfit/period/meeting/gift/health/mood/milestone/contact/hobby/social，
    date_from / date_to: YYYY-MM-DD。
    """
    params: Dict[str, Any] = {"limit": limit, "type_key": type_key,
                              "date_from": date_from, "date_to": date_to, "q": q}
    if who:
        params["person_id"] = _resolve(who)["id"]
    res = _call("GET", "/api/events", params=params) or {}
    items = res.get("items") or []
    if not items:
        return "（没有记录）"
    return "共 %s 条，显示 %d 条：\n" % (res.get("total"), len(items)) + \
        "\n".join(_ev_line(e) for e in items)


@mcp.tool()
@_safe
def search(q: str, who: Optional[str] = None, limit: int = 20) -> str:
    """全库检索记录正文（中文；1-2 字的短词会走 LIKE 回退）。"""
    params: Dict[str, Any] = {"q": q, "limit": limit}
    if who:
        params["person_id"] = _resolve(who)["id"]
    res = _call("GET", "/api/search", params=params) or {}
    mode = res.get("mode", "?") if isinstance(res, dict) else "?"
    hits = (res.get("items") if isinstance(res, dict) else res) or []
    if not hits:
        return "（没有命中「%s」，检索方式=%s）" % (q, mode)
    return "命中 %d 条（检索方式=%s）：\n" % (len(hits), mode) + "\n".join(
        "#%s %s [%s] %s %s%s" % (h["id"], _when(h), h.get("type_key"),
                                 h.get("person_name") or "", h.get("title") or "",
                                 (" — %s" % h["snippet"]) if h.get("snippet") else "")
        for h in hits)


@mcp.tool()
@_safe
def relations(who: Optional[str] = None) -> str:
    """人与人之间的关系边。不给 who 就返回全部。"""
    params = {"person_id": _resolve(who)["id"]} if who else None
    rels = _call("GET", "/api/relations", params=params) or []
    if not rels:
        return "（没有关系记录）"
    return "\n".join("#%d %s —%s→ %s%s" % (r["id"], r["from_name"], r["label"], r["to_name"],
                                          ("（%s）" % r["notes"]) if r.get("notes") else "")
                     for r in rels)


@mcp.tool()
@_safe
def anniversaries() -> str:
    """纪念日与生日的倒计时（已过多少天 / 距下次多少天）。"""
    card = _call("GET", "/api/today") or {}
    lines = ["今天：%s %s（%s）" % (card.get("date"), card.get("weekday", ""), card.get("lunar", ""))]
    for a in card.get("anniversaries") or []:
        lines.append("  %s：%s（已 %s 天，距下次 %s 天）" % (
            a.get("person_name") or "", a.get("title"), a.get("days_since"), a.get("days_to_next")))
    for s in card.get("special_notes") or []:
        lines.append("  ⭐ " + str(s))
    return "\n".join(lines)


@mcp.tool()
@_safe
def upcoming(days: int = 10, who: Optional[str] = None) -> str:
    """未来 N 天要留意的事：待办到期、生日、纪念日、经期预测。"""
    params: Dict[str, Any] = {"days": days}
    if who:
        params["person_id"] = _resolve(who)["id"]
    res = _call("GET", "/api/upcoming", params=params) or {}
    items = res.get("items") if isinstance(res, dict) else res
    if not items:
        return "未来 %d 天没有安排/提醒。" % days
    return json.dumps(items, ensure_ascii=False, indent=1)


@mcp.tool()
@_safe
def todos(who: Optional[str] = None, include_done: bool = False) -> str:
    """待办清单（默认只看未完成）。"""
    params: Dict[str, Any] = {"include_done": "true" if include_done else None}
    if who:
        params["person_id"] = _resolve(who)["id"]
    rows = _call("GET", "/api/todos", params=params) or []
    if not rows:
        return "（没有待办）" if include_done else "（没有未完成待办）"
    return "共 %d 条待办：\n" % len(rows) + "\n".join("#%d [%s]%s %s%s" % (
        t["id"], "✓" if t["done"] else " ", (" %s:" % t["person_name"]) if t.get("person_name") else "",
        t["title"], (" · 截止 %s" % t["due_date"]) if t.get("due_date") else "") for t in rows)


@mcp.tool()
@_safe
def cycle_prediction(who: str) -> str:
    """生理期预测（仅供关怀提醒，不能用于避孕/安全期判断）。"""
    return json.dumps(_call("GET", "/api/cycle/prediction", params={"person_id": _resolve(who)["id"]}),
                      ensure_ascii=False, indent=1)


@mcp.tool()
@_safe
def stats() -> str:
    """服务总览：人物数、记录数、待办数、媒体占用等。"""
    return json.dumps({
        "overview": _call("GET", "/api/stats/overview"),
        "media_storage": _call("GET", "/api/media/storage"),
    }, ensure_ascii=False, indent=1)


@mcp.tool()
@_safe
def wardrobe_items(who: Optional[str] = None, category: Optional[str] = None,
                   q: Optional[str] = None, include_duplicates: bool = False,
                   status: Optional[str] = None, include_offhand: bool = False) -> str:
    """衣橱：单品清单（一行一件，带「穿过几次 / 最近一次 / 状态」）。

    category: top 上衣 / bottom 下装 / outer 外套马甲 / dress 裙装 /
              shoes 鞋 / accessory 配饰 / bag 包 / other 其他。
    status: in_use 在役 / idle 闲置收纳 / sold 已卖出 / gifted 已送人 /
            lost 已丢失 / damaged 损坏待修 / discarded 已丢弃。
    默认只列「在手」（在役 + 闲置）；要查已卖出/送人的旧物，传 include_offhand=True。
    include_duplicates=True 时附「疑似重复」候选 —— 去重只出候选，合并必须人工确认。
    """
    params: Dict[str, Any] = {"category": category, "q": q, "status": status}
    if include_offhand:
        params["include_offhand"] = "true"
    if who:
        params["person_id"] = _resolve(who)["id"]
    data = _call("GET", "/api/wardrobe/items", params=params) or {}
    rows = data.get("items") or []
    if not rows:
        return "衣橱里还没有单品（记一次穿搭或新建单品后再看）。"
    lines = []
    for it in rows:
        bits = ["#%s [%s] %s" % (it["id"], it.get("category_label") or it["category"], it["name"])]
        bits.append("颜色=%s" % (it.get("color") or "未填"))
        bits.append("穿过 %s 次" % it.get("wear_count", 0))
        if it.get("last_worn_on"):
            bits.append("最近=%s" % it["last_worn_on"])
        if it.get("status") and it["status"] != "in_use":
            bits.append("[%s]" % (it.get("status_label") or it["status"]))
        if it.get("status_reason"):
            bits.append("原因=%s" % it["status_reason"])
        if it.get("added_on"):
            bits.append("加入=%s" % it["added_on"])
        if it.get("merged_into_id"):
            bits.append("[已合并]")
        if it.get("person_name"):
            bits.append(it["person_name"])
        lines.append(" ".join(bits))
    out = "共 %d 件：\n" % len(rows) + "\n".join(lines)
    if include_duplicates:
        dup = _call("GET", "/api/wardrobe/duplicates", params=params) or {}
        groups = dup.get("groups") or []
        if groups:
            out += "\n\n疑似重复 %d 组（合并要人工确认）：\n" % len(groups)
            out += "\n".join(
                "- [%s] %s → %s" % (
                    g["confidence"], g["reason"],
                    " / ".join("#%s %s（穿%s次）" % (i["id"], i["name"], i["wear_count"])
                               for i in g["items"]))
                for g in groups)
    return out


@mcp.tool()
@_safe
def wardrobe_item(item_id: int) -> str:
    """单品档案卡：属性 + 穿着历史（哪天穿的、当时还穿了什么）。"""
    d = _call("GET", "/api/wardrobe/items/%d" % item_id)
    head = "#%s %s（%s / 颜色=%s）穿过 %s 次" % (
        d["id"], d["name"], d.get("category_label") or d["category"],
        d.get("color") or "未填", d.get("wear_count", 0))
    if d.get("person_name"):
        head += " · %s" % d["person_name"]
    if d.get("tags"):
        head += " · 标签=%s" % d["tags"]
    if d.get("notes"):
        head += "\n备注：%s" % d["notes"]
    if d.get("merged_into_id"):
        head += "\n[这条已合并到 #%s]" % d["merged_into_id"]
    head += "\n状态：%s" % (d.get("status_label") or d.get("status"))
    if d.get("status_reason"):
        head += "（%s）" % d["status_reason"]
    if d.get("status_changed_on"):
        head += " · 自 %s" % d["status_changed_on"]
    if d.get("added_at"):
        head += " · 加入衣橱 %s" % d["added_at"]
    if d.get("replaces"):
        head += "\n替代了：#%s %s（%s）" % (
            d["replaces"]["id"], d["replaces"]["name"], d["replaces"].get("status_label"))
    if d.get("replaced_by"):
        head += "\n被替代：" + "、".join(
            "#%s %s（%s）" % (r["id"], r["name"], r.get("status_label"))
            for r in d["replaced_by"])
    wears = d.get("wears") or []
    if not wears:
        return head + "\n还没有穿着记录（可能只是「提起过」）。"
    lines = [head, "穿着历史 %d 次：" % len(wears)]
    for w in wears:
        line = "- %s（%s）" % (w["event_date"], w.get("slot"))
        if w.get("together"):
            line += " 和 " + "、".join(w["together"])
        if w.get("note"):
            line += " —— %s" % w["note"]
        if w.get("media"):
            line += "（照片 %d 张）" % len(w["media"])
        lines.append(line)
    return "\n".join(lines)


# ------------------------------------------------------------------ 写工具

@mcp.tool()
@_safe
def add_event(who: str, title: str, type_key: str = "text",
              event_date: Optional[str] = None, event_time: Optional[str] = None,
              body: Optional[str] = None,
              tags: Optional[str] = None, location: Optional[str] = None,
              overnight: Optional[bool] = None, hours: Optional[float] = None,
              ended_on: Optional[str] = None,
              also_with: Optional[str] = None) -> str:
    """给某人记一条记录（不指定日期就是今天；不指定时间就记此刻）。

    type_key: text 文字 / outfit 服装 / period 生理期 / meeting 相处 / gift 礼物 /
    health 健康 / mood 情绪 / milestone 里程碑 / contact 联系 / hobby 爱好 / social 社交。
    event_date: YYYY-MM-DD；event_time: HH:MM 或 HH:MM:SS（记到过去某天又没说时间 → 只记到日）。
    ended_on: 仅 meeting 用，跨日相处的结束日 YYYY-MM-DD（不传 = 单日）。
      跨日记录自动算过夜、忽略 hours；与 event_date 同一天等价于不传。
    注意：模块开关只在网页端做拦截，服务端与这里都不校验 —— 传了这个人没开的类型
    也会写进去，请自己确认类型合适（拿不准就先 person() 看模块）。
    also_with: 同时在场的人（三人场合），逗号分隔姓名。
    """
    _require_write()
    p = _resolve(who)
    payload: Dict[str, Any] = {
        "person_id": p["id"], "type_key": type_key,
        "event_date": event_date or _today(), "title": title,
        "event_time": _default_event_time(event_date, event_time),
        "body": body, "tags": tags, "source": "mcp",
    }
    if type_key == "meeting":
        payload.update({"location": location, "overnight": overnight, "hours": hours,
                        "ended_on": ended_on})
    if also_with:
        ids = [p["id"]] + [_resolve(x.strip())["id"] for x in also_with.replace("、", ",").split(",") if x.strip()]
        payload["person_ids"] = sorted(set(ids))
    created = _call("POST", "/api/events", body=payload)
    return "已记录 #%s：%s %s %s" % (created["id"], _when(created), created["type_key"], created["title"])


@mcp.tool()
@_safe
def add_outfit(who: str, items: str, event_date: Optional[str] = None,
               event_time: Optional[str] = None,
               note: Optional[str] = None, location: Optional[str] = None) -> str:
    """记一次穿搭：items = 穿了哪几件（逗号分隔）。

    已有的单品**自动复用**（不会重复建），没有的自动新建；穿次数随之累加。
    名称可带类别前缀，如 `下装:黑色阔腿裤, 上衣:白色毛衣`；不带前缀时先按名字找已有单品，
    找不到会建到「其他」类别（之后可在衣橱页改类别）。
    不指定日期就是今天、不指定时间就记此刻（过去某天只记到日）。
    """
    _require_write()
    p = _resolve(who)
    existing = _call("GET", "/api/wardrobe/items", params={"person_id": p["id"]}) or {}
    by_name = {}
    for it in existing.get("items", []):
        by_name.setdefault(str(it["name"]).replace(" ", ""), it)
    refs: List[Dict[str, Any]] = []
    for raw in items.replace("、", ",").split(","):
        token = raw.strip()
        if not token:
            continue
        if ":" in token or "：" in token:
            cat, _, nm = token.replace("：", ":").partition(":")
            refs.append({"category": cat.strip(), "name": nm.strip()})
            continue
        hit = by_name.get(token.replace(" ", ""))
        refs.append({"item_id": hit["id"]} if hit else {"name": token})
    if not refs:
        raise RuntimeError("items 不能为空（逗号分隔的单品名）")
    created = _call("POST", "/api/outfits", body={
        "person_id": p["id"], "event_date": event_date or _today(),
        "event_time": _default_event_time(event_date, event_time),
        "items": refs, "note": note, "location": location, "source": "mcp",
    })
    names = "、".join(i["name"] for i in created["items"])
    return "已记穿搭 #%s：%s %s（引用 %d 件单品）" % (
        created["id"], _when(created), names, len(created["items"]))


@mcp.tool()
@_safe
def set_wardrobe_status(item_id: int, status: str, reason: Optional[str] = None,
                        effective_date: Optional[str] = None) -> str:
    """改单品状态：在役 / 闲置收纳 / 已卖出 / 已送人 / 已丢失 / 损坏待修 / 已丢弃。

    status: in_use / idle / sold / gifted / lost / damaged / discarded。
    离手状态（sold/gifted/lost/damaged/discarded）建议写一句 reason（卖给谁、给了谁、
    换成了什么）；不写也能改，但半年后没人说得清为什么。
    effective_date: YYYY-MM-DD，不传 = 今天。每次改状态都会追加一条历史，不覆盖旧原因。
    ★ 「卖掉又换了新的」：改完旧件状态后，新建新件时要指回旧件（网页编辑页的「替代了哪件」），
      这样两边都能看到替换关系。
    """
    _require_write()
    payload: Dict[str, Any] = {"status": status}
    if reason:
        payload["status_reason"] = reason
    if effective_date:
        payload["status_changed_on"] = effective_date
    d = _call("PATCH", "/api/wardrobe/items/%d" % item_id, body=payload)
    line = "已改 #%s %s → %s" % (d["id"], d["name"], d.get("status_label") or d["status"])
    if d.get("status_reason"):
        line += "（%s）" % d["status_reason"]
    if d.get("status_changed_on"):
        line += " · 自 %s" % d["status_changed_on"]
    return line


@mcp.tool()
@_safe
def add_todo(title: str, who: Optional[str] = None, kind: str = "missing_info",
             detail: Optional[str] = None, due_date: Optional[str] = None) -> str:
    """加一条待办（due_date 传 YYYY-MM-DD 可设提醒日期）。"""
    _require_write()
    payload: Dict[str, Any] = {"title": title, "kind": kind, "detail": detail, "due_date": due_date}
    if who:
        payload["person_id"] = _resolve(who)["id"]
    created = _call("POST", "/api/todos", body=payload)
    return "已加待办 #%s：%s" % (created["id"], created["title"])


@mcp.tool()
@_safe
def todo_done(todo_id: int) -> str:
    """把待办标记为已完成（或再点一次改回未完成）。"""
    _require_write()
    rows = _call("GET", "/api/todos", params={"include_done": "true"}) or []
    cur = next((t for t in rows if t["id"] == todo_id), None)
    if not cur:
        raise RuntimeError("没有 #%d 这条待办" % todo_id)
    updated = _call("PATCH", "/api/todos/%d" % todo_id, body={"done": not cur["done"]})
    return "待办 #%s 现在：%s" % (updated["id"], "已完成" if updated["done"] else "未完成")


@mcp.tool()
@_safe
def add_attribute(who: str, category: str, value: str, note: Optional[str] = None) -> str:
    """记一条属性（爱好/忌口/尺码/喜欢的东西这类 KV）。

    category 常见值：like 喜欢 / dislike 忌口 / drink 饮品 / observe 观察 / experience 体验 / size 尺码。
    """
    _require_write()
    p = _resolve(who)
    created = _call("POST", "/api/attributes",
                    body={"person_id": p["id"], "category": category, "value": value, "note": note})
    return "已记属性 #%s：%s = %s" % (created["id"], created["category"], created["value"])


@mcp.tool()
@_safe
def add_cycle(who: str, start_date: Optional[str] = None, end_date: Optional[str] = None,
              flow: Optional[str] = None, symptoms: Optional[str] = None,
              note: Optional[str] = None) -> str:
    """记一次生理期（默认今天开始）。只有关怀提醒用途。"""
    _require_write()
    p = _resolve(who)
    created = _call("POST", "/api/cycle", body={
        "person_id": p["id"], "start_date": start_date or _today(),
        "end_date": end_date, "flow": flow, "symptoms": symptoms, "note": note,
    })
    return "已记生理期 #%s：%s 起" % (created["id"], created["start_date"])


@mcp.tool()
@_safe
def add_person(name: str, relation_type: str = "friend", circle: str = "self",
               gender: Optional[str] = None, birthday: Optional[str] = None, lunar: bool = False,
               lunar_month: Optional[int] = None, lunar_day: Optional[int] = None,
               aliases: Optional[str] = None, notes: Optional[str] = None,
               via: Optional[str] = None, familiarity: int = 1,
               sensitivity: str = "normal") -> str:
    """新建一个人物档案。

    relation_type: partner/family/friend/colleague/acquaintance/self，
    gender: female/male/other（不传 = 未知；只有「伴侣 + 女」会自动开生理期模块），
    circle: self/partner/shared，via: 通过谁认识（姓名），
    birthday 传公历 YYYY-MM-DD；农历生日就传 lunar=True + lunar_month/lunar_day。
    """
    _require_write()
    payload: Dict[str, Any] = {
        "display_name": name, "relation_type": relation_type, "circle": circle,
        "gender": gender, "birthday": birthday, "birthday_lunar": lunar,
        "lunar_month": lunar_month, "lunar_day": lunar_day,
        "aliases": aliases, "notes": notes, "familiarity": familiarity,
        "sensitivity": sensitivity,
    }
    if via:
        payload["via_person_id"] = _resolve(via)["id"]
    created = _call("POST", "/api/persons", body=payload)
    return "已建人物 #%s：%s（%s / %s）" % (created["id"], created["display_name"],
                                          created["relation_type"], created["circle"])


if __name__ == "__main__":
    sys.stderr.write("kinship-archive MCP server 启动（%s，写=%s）\n"
                     % (BASE_URL, "开" if WRITE_ENABLED else "关"))
    mcp.run()
