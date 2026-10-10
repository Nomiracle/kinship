"""MCP server 冒烟测试：真的把 server 当子进程拉起来，走 stdio 协议调工具。

跑法（在 app/ 目录）：
    set -a; . ../deploy/.env; set +a
    ARCHIVE_TOKEN="$ARCHIVE_TOKEN" .venv/bin/python tests/mcp_smoke.py

它自己建一个临时人物当测试对象，结束时删掉 —— 不依赖也不污染真实数据。
写工具在 KINSHIP_MCP_WRITE=0 时会被跳过（只测读）。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

APP_DIR = Path(__file__).resolve().parent.parent
BASE = os.environ.get("KINSHIP_ARCHIVE_URL", "http://127.0.0.1:8787")
TOKEN = os.environ.get("ARCHIVE_TOKEN") or os.environ.get("KINSHIP_ARCHIVE_TOKEN", "")
TEST_NAME = "MCP冒烟测试-临时人物"

EXPECTED_TOOLS = {
    # 读
    "people", "person", "timeline", "search", "relations", "anniversaries",
    "upcoming", "todos", "cycle_prediction", "stats", "wardrobe_items", "wardrobe_item",
    # 写
    "add_event", "add_todo", "todo_done", "add_attribute", "add_cycle", "add_person",
    "add_outfit",
}

PASS, FAIL = [], []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(label)
    print("  %s %s%s" % ("✓" if ok else "✗", label, ("  ← " + detail) if (detail and not ok) else ""))


def api(method: str, path: str, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-Archive-Token", TOKEN)
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else None


def cleanup() -> None:
    """删掉测试人物（连带其事件/待办/属性/生理期）。"""
    try:
        for p in api("GET", "/api/persons?include_inactive=true"):
            if p["display_name"].startswith(TEST_NAME):
                api("DELETE", "/api/persons/%d" % p["id"])
    except Exception as e:  # noqa: BLE001
        print("  ! 清理失败（请手工删「%s」）：%s" % (TEST_NAME, e))


def text_of(result) -> str:
    """把 CallToolResult 里的文本拼出来（content 是 [TextContent(...)]）。"""
    out = []
    for item in getattr(result, "content", []) or []:
        out.append(getattr(item, "text", "") or "")
    return "\n".join(x for x in out if x)


async def main() -> None:
    write_enabled = os.environ.get("KINSHIP_MCP_WRITE", "1") not in ("0", "false", "False")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.mcp_server"],
        cwd=str(APP_DIR),
        env={**os.environ},
    )
    cleanup()  # 上次跑挂了可能留残留

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            check("工具清单齐全（%d 个）" % len(EXPECTED_TOOLS),
                  EXPECTED_TOOLS <= names, "缺少: %s" % sorted(EXPECTED_TOOLS - names))
            check("每个工具都有说明（LLM 靠它选工具）",
                  all((t.description or "").strip() for t in tools.tools),
                  "没描述: %s" % [t.name for t in tools.tools if not (t.description or "").strip()])
            check("没有删除类工具（删除只在网页做）",
                  not any(("delete" in n or "remove" in n) for n in names), str(sorted(names)))

            # ---- 读 ----
            r = text_of(await session.call_tool("people", {}))
            check("people 能列出人物", "ID" not in r and len(r) > 0, r[:120])
            r = text_of(await session.call_tool("anniversaries", {}))
            check("anniversaries 有内容", "今天" in r, r[:120])
            r = text_of(await session.call_tool("todos", {}))
            check("todos 有内容或明确为空", ("待办" in r) or ("没有待办" in r), r[:120])
            r = text_of(await session.call_tool("stats", {}))
            check("stats 返回概览 JSON", "overview" in r, r[:120])
            r = text_of(await session.call_tool("person", {"who": "不存在的名字-xyz"}))
            check("查不到人时给的是可读错误", "找不到" in r, r[:160])

            if not write_enabled:
                print("\n  （KINSHIP_MCP_WRITE=0，跳过写工具测试）")
            else:
                # ---- 写：建人 → 记事件/属性/生理期/待办 → 回读 → 完成待办 ----
                r = text_of(await session.call_tool("add_person", {
                    "name": TEST_NAME, "relation_type": "partner", "circle": "shared",
                    "birthday": "1990-01-02", "aliases": "mcp测试、临时",
                }))
                check("add_person 建人成功", TEST_NAME in r, r[:160])
                pid = None
                for p in api("GET", "/api/persons"):
                    if p["display_name"] == TEST_NAME:
                        pid = p["id"]
                check("新建的人能被 API 读到（没绕过服务端）", pid is not None, str(pid))

                r = text_of(await session.call_tool("add_event", {
                    "who": TEST_NAME, "title": "MCP 冒烟事件", "type_key": "text",
                    "body": "由 mcp_server 写入", "tags": "mcp,smoke",
                }))
                check("add_event 写事件成功", "已记录" in r, r[:160])
                r = text_of(await session.call_tool("add_attribute", {
                    "who": TEST_NAME, "category": "like", "value": "MCP测试值",
                }))
                check("add_attribute 写属性成功", "已记属性" in r, r[:160])
                r = text_of(await session.call_tool("add_cycle", {"who": TEST_NAME}))
                check("add_cycle 写生理期成功（模块默认开了才有）", "已记生理期" in r, r[:160])
                r = text_of(await session.call_tool("add_todo", {
                    "title": "MCP 冒烟待办", "who": TEST_NAME}))
                check("add_todo 写待办成功", "已加待办" in r, r[:160])
                todo_id = None
                for t in api("GET", "/api/todos?include_done=true"):
                    if t["title"] == "MCP 冒烟待办":
                        todo_id = t["id"]
                r = text_of(await session.call_tool("todo_done", {"todo_id": todo_id}))
                check("todo_done 标记完成", "已完成" in r, r[:160])

                # 按写进去的名字回读：证明 aliases 解析 + 读工具串通
                r = text_of(await session.call_tool("person", {"who": "mcp测试"}))
                check("按别名查得到这个人（别名解析）", TEST_NAME in r, r[:160])
                r = text_of(await session.call_tool("timeline", {"who": "临时", "limit": 5}))
                check("timeline 按人过滤能查到刚写的事件", "MCP 冒烟事件" in r, r[:200])
                r = text_of(await session.call_tool("search", {"q": "MCP 冒烟"}))
                check("search 能搜到刚写的事件", "MCP 冒烟事件" in r, r[:200])
                r = text_of(await session.call_tool("cycle_prediction", {"who": TEST_NAME}))
                check("cycle_prediction 可用", "{" in r, r[:160])
                r = text_of(await session.call_tool("upcoming", {"days": 30}))
                check("upcoming 可用", len(r) > 0, r[:120])

                # ---- 服装：穿搭 + 单品（去重在「同一件只存一条」）----
                r = text_of(await session.call_tool("add_outfit", {
                    "who": TEST_NAME, "items": "top:MCP冒烟上衣, bottom:MCP冒烟长裤",
                    "note": "mcp 冒烟"}))
                check("add_outfit 记穿搭成功", "已记穿搭" in r and "引用 2 件" in r, r[:200])
                items = api("GET", "/api/wardrobe/items?person_id=%d" % pid)["items"]
                check("穿搭自动建了 2 件单品", len(items) == 2, str([i["name"] for i in items]))
                check("单品记录了穿着次数", all(i["wear_count"] == 1 for i in items), str(items))

                # 同一件再穿一次：必须复用，不能新建
                r = text_of(await session.call_tool("add_outfit", {
                    "who": TEST_NAME, "items": "MCP冒烟上衣, MCP冒烟长裤"}))
                check("按名字复用已有单品（不新建）", "引用 2 件" in r, r[:200])
                items = api("GET", "/api/wardrobe/items?person_id=%d" % pid)["items"]
                check("单品数仍是 2（没有重复建）", len(items) == 2, str([i["name"] for i in items]))
                check("穿着次数累加到 2", all(i["wear_count"] == 2 for i in items), str(items))

                r = text_of(await session.call_tool("wardrobe_items", {"who": TEST_NAME}))
                check("wardrobe_items 列出单品与次数", "MCP冒烟上衣" in r and "穿过 2 次" in r, r[:240])
                r = text_of(await session.call_tool("wardrobe_item", {"item_id": items[0]["id"]}))
                check("wardrobe_item 给档案例 + 穿着历史",
                      "穿着历史" in r and "2 次" in r, r[:240])
                r = text_of(await session.call_tool("wardrobe_items",
                                                    {"who": TEST_NAME, "include_duplicates": True}))
                check("wardrobe_items 可附疑似重复候选", "MCP冒烟" in r, r[:240])

                # 模块开关只在网页端拦；服务端与 MCP 都不校验（有意为之，见 add_event 文档）
                r = text_of(await session.call_tool("add_event", {
                    "who": TEST_NAME, "title": "模块未开也能写", "type_key": "contact"}))
                check("模块开关不拦写入（已知设计：只在网页端拦）", "已记录" in r, r[:200])

    cleanup()
    check("测试数据已清理", all(p["display_name"] != TEST_NAME for p in api("GET", "/api/persons?include_inactive=true")))

    print("\n== MCP 冒烟：%d 通过 / %d 失败 ==" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：" + "; ".join(FAIL))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
