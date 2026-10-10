#!/usr/bin/env python3
"""对运行中的实例做端到端冒烟测试（纯标准库，可公开）。

用法：
    ARCHIVE_TOKEN=... BASE=http://127.0.0.1:8787 python3 tests/smoke_api.py

会创建一批带前缀的临时数据，跑完全部删掉 —— 不污染真实档案。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
from make_fixture import png_bytes  # noqa: E402  —— 合成图片，仓库内无真实照片

BASE = os.environ.get("BASE", "http://127.0.0.1:8787").rstrip("/")
TOKEN = os.environ.get("ARCHIVE_TOKEN", "")
PREFIX = "__smoke__"

passed, failed = [], []


def call(method: str, path: str, payload=None, token: str | None = TOKEN, expect: int = 200,
         raw: tuple | None = None):
    """raw=(body_bytes, content_type) 时直接发原始体（多部分上传用）。"""
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("X-Archive-Token", token)
    data = None
    if raw is not None:
        data, ctype = raw
        req.add_header("Content-Type", ctype)
    elif payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=15) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if not ctype.startswith("application/json") and not ctype.startswith("text/"):
                # 二进制（图片/视频）不尝试解析，只报大小与类型
                return resp.status, {"bytes": len(body), "content_type": ctype}
            text = body.decode("utf-8", "replace")
            return resp.status, (json.loads(text) if text.strip() else None)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body.decode("utf-8", "replace"))
        except Exception:
            return exc.code, body[:200].decode("utf-8", "replace")


def head(path: str, accept_encoding: str | None = None, token: str | None = TOKEN):
    """取原始响应（状态码 + 小写响应头 + body）—— 用来断言压缩与缓存策略。

    call() 会把 text/* 当 JSON 解析，对 HTML 会抛错，所以这类断言走这里。
    """
    req = urllib.request.Request(BASE + path, method="GET")
    if token:
        req.add_header("X-Archive-Token", token)
    if accept_encoding:
        req.add_header("Accept-Encoding", accept_encoding)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, headers, exc.read()


def check(name: str, cond: bool, detail: str = "") -> None:
    (passed if cond else failed).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + ((" — " + detail) if detail and not cond else ""))


def multipart(fields: dict, files: dict) -> tuple:
    """手搓 multipart/form-data（纯标准库，避免为测试引依赖）。"""
    boundary = "----smoke" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(
            ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
             % (boundary, k, v)).encode()
        )
    for k, (fname, content, ctype) in files.items():
        parts.append(
            ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
             'Content-Type: %s\r\n\r\n' % (boundary, k, fname, ctype)).encode()
        )
        parts.append(content + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode())
    return b"".join(parts), "multipart/form-data; boundary=%s" % boundary


def main() -> int:
    today = dt.date.today()
    print("== 冒烟测试 %s ==" % BASE)

    # --- 认证 ---
    st, _ = call("GET", "/api/health", token=None)
    check("health 免口令可访问", st == 200, "status=%s" % st)
    st, _ = call("GET", "/api/persons", token=None)
    check("无口令被拒 401", st == 401, "status=%s" % st)
    st, _ = call("GET", "/api/persons", token="definitely-wrong")
    check("错口令被拒 401", st == 401, "status=%s" % st)
    st, _ = call("GET", "/api/config")
    check("正口令可访问", st == 200, "status=%s" % st)

    # --- 传输层：手机经 Tailscale（DERP 中继，单程 RTT ~400ms）访问时，
    #     首屏体积与缓存策略直接决定「点一下要等多久」---
    st, h, html = head("/")
    check("index.html 不缓存（部署后手机才拿得到新版本）",
          st == 200 and "no-cache" in (h.get("cache-control") or ""),
          "cache-control=%s" % h.get("cache-control"))
    m = re.search(rb"/assets/(index-[^\"']+\.js)", html or b"")
    if m:
        asset = m.group(1).decode()
        st_a, h_a, _ = head("/assets/" + asset, accept_encoding="gzip")
        check("入口 JS 有 gzip（首屏 ~3x 压缩）",
              h_a.get("content-encoding") == "gzip", "content-encoding=%s" % h_a.get("content-encoding"))
        check("带哈希资源可长缓存（immutable）",
              "immutable" in (h_a.get("cache-control") or ""),
              "cache-control=%s" % h_a.get("cache-control"))
    else:
        check("首页引用了入口 JS（构建产物完整）", False, "index.html 里找不到 /assets/index-*.js")
    st_j, h_j, _ = head("/api/events?limit=200", accept_encoding="gzip")
    check("API 大响应有 gzip", h_j.get("content-encoding") == "gzip",
          "content-encoding=%s" % h_j.get("content-encoding"))

    created_persons, created_events, created_todos, created_media = [], [], [], []
    created_relations = []
    files_before = 0

    try:
        # --- 人 + 模块默认值 ---
        st, self_p = call("POST", "/api/persons", {
            "display_name": PREFIX + "我", "relation_type": "self", "is_self": True,
        })
        check("建 self 人物", st == 201, "status=%s %s" % (st, self_p))
        created_persons.append(self_p["id"])

        st, p = call("POST", "/api/persons", {
            "display_name": PREFIX + "伴侣", "relation_type": "partner",
            "birthday": "1990-01-01", "birthday_lunar": False,
        })
        check("建 partner 人物", st == 201, "status=%s %s" % (st, p))
        created_persons.append(p["id"])

        st, mods = call("GET", "/api/persons/%d/modules" % p["id"])
        check("partner 自动获得默认模块（含 cycle）",
              "cycle" in (mods or {}).get("enabled", []), str(mods))

        # --- 属性 KV ---
        st, attr = call("POST", "/api/attributes", {
            "person_id": p["id"], "category": "avoid", "value": PREFIX + "香菜",
        })
        check("加属性（忌口）", st == 201, "status=%s %s" % (st, attr))
        if isinstance(attr, dict) and attr.get("id"):
            call("DELETE", "/api/attributes/%d" % attr["id"], expect=204)

        # --- 文字记录 ---
        st, e1 = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text", "event_date": today.isoformat(),
            "title": PREFIX + "文字标题", "body": PREFIX + "棕色马甲与黑色裙子，心情不错",
            "tags": PREFIX + "tag",
        })
        check("建文字记录", st == 201, "status=%s %s" % (st, e1))
        created_events.append(e1["id"])

        # --- 生理期（扇出到 cycle_records）---
        st, e2 = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "period",
            "event_date": (today - dt.timedelta(days=30)).isoformat(),
            "title": PREFIX + "周期1",
        })
        check("建生理期记录", st == 201, "status=%s %s" % (st, e2))
        created_events.append(e2["id"])
        st, cyc = call("GET", "/api/cycle?person_id=%d" % p["id"])
        check("生理期扇出到 cycle_records",
              isinstance(cyc, list) and any(PREFIX in (c.get("note") or "") for c in cyc),
              str(cyc))
        st, pred = call("GET", "/api/cycle/prediction?person_id=%d" % p["id"])
        check("周期预测可算（含 ± 提示）",
              st == 200 and "误差" in (pred or {}).get("note", ""), str(pred))

        # --- 相处 / 过夜（扇出到 interactions）---
        st, e3 = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "meeting",
            "event_date": (today - dt.timedelta(days=3)).isoformat(),
            "title": PREFIX + "见面", "overnight": True, "location": PREFIX + "某地",
        })
        check("建相处记录（过夜）", st == 201, "status=%s %s" % (st, e3))
        created_events.append(e3["id"])
        st, inter = call("GET", "/api/interactions?person_id=%d" % p["id"])
        check("相处扇出到 interactions 且 overnight=True",
              isinstance(inter, list) and inter and inter[0].get("overnight") is True,
              str(inter))

        # --- 时间轴 / 今天 / 搜索 ---
        st, tl = call("GET", "/api/events?person_id=%d" % p["id"])
        check("时间轴返回三类记录",
              st == 200 and tl.get("total", 0) >= 3, str(tl)[:200])

        st, td = call("GET", "/api/today?person_id=%d" % p["id"])
        check("今天卡片含农历与本人",
              st == 200 and td.get("lunar") and td.get("persons"), str(td)[:200])

        st, s1 = call("GET", "/api/search?q=%s" % urllib.parse.quote(PREFIX + "棕色"))
        check("多字搜索走全文索引（fulltext）",
              st == 200 and s1.get("mode") == "fulltext" and s1.get("items"), str(s1)[:200])

        st, s2 = call("GET", "/api/search?q=%s" % urllib.parse.quote("棕"))
        check("单字搜索回退 LIKE（ngram 单字必然 0 命中）",
              st == 200 and "like" in str(s2.get("mode")), str(s2)[:200])

        # --- 「我」的删除保护：有记录时不允许删，清空后允许 ---
        st, e_self = call("POST", "/api/events", {
            "person_id": self_p["id"], "type_key": "text", "event_date": today.isoformat(),
            "title": PREFIX + "我自己的记录",
        })
        created_events.append(e_self["id"])
        st, err = call("DELETE", "/api/persons/%d" % self_p["id"])
        check("「我」有记录时删除被拒 400", st == 400, "status=%s %s" % (st, err))
        call("DELETE", "/api/events/%d" % e_self["id"], expect=204)
        created_events.remove(e_self["id"])

        # --- 待办 ---
        st, t = call("POST", "/api/todos", {
            "person_id": p["id"], "kind": "missing_info", "title": PREFIX + "待补信息",
        })
        check("建待办", st == 201, "status=%s %s" % (st, t))
        created_todos.append(t["id"])
        st, t2 = call("PATCH", "/api/todos/%d" % t["id"], {"done": True})
        check("待办可标记完成", st == 200 and t2.get("done") is True, str(t2))

        # --- 统计 ---
        st, ov = call("GET", "/api/stats/overview")
        check("统计接口可用", st == 200 and "events_by_type" in (ov or {}), str(ov)[:200])

        # --- 媒体（图片上传 + 口令路由 + 挂到事件）---
        st, storage0 = call("GET", "/api/media/storage")
        files_before = (storage0 or {}).get("files", 0)

        st, e_img = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "outfit", "event_date": today.isoformat(),
            "title": PREFIX + "带图穿搭", "tags": PREFIX + "棕色",
        })
        check("建服装记录（待挂图）", st == 201, "status=%s %s" % (st, e_img))
        created_events.append(e_img["id"])

        png = png_bytes(1200, 900, (124, 92, 60))     # 大图 → 应生成缩略图
        st, up = call("POST", "/api/media",
                      raw=multipart({"person_id": str(p["id"]), "event_id": str(e_img["id"]),
                                     "captured_on": today.isoformat()},
                                    {"file": ("smoke.png", png, "image/png")}))
        check("上传图片（multipart）", st == 201 and up and up[0].get("thumb_path"),
              "status=%s %s" % (st, up))
        if st == 201:
            m = up[0]
            created_media.append(m["id"])
            st2, _ = call("GET", "/media/%s" % m["thumb_path"])
            check("缩略图经鉴权可取（Cookie/头）", st2 == 200, "status=%s" % st2)
            st3, _ = call("GET", "/media/%s" % m["thumb_path"], token="definitely-wrong")
            check("错误口令取图被拒 401", st3 == 401, "status=%s" % st3)
            st3b, _ = call("GET", "/media/%s" % m["thumb_path"], token=None)
            check("无口令取图被拒 401", st3b == 401, "status=%s" % st3b)
            st_n, h_n, _ = head("/media/%s" % (m.get("thumb_path") if isinstance(m, dict) else ""),
                                accept_encoding="gzip")
            check("图片不被 gzip 二次编码（省 CPU、保住 ETag）",
                  st_n == 200 and not h_n.get("content-encoding"),
                  "content-encoding=%s" % h_n.get("content-encoding"))

            # 小图不得生成缩略图（sips -Z 会把小图放大，曾经就是这么踩的）
            st_small, up_small = call("POST", "/api/media",
                                      raw=multipart({"person_id": str(p["id"])},
                                                    {"file": ("small.png", png_bytes(64, 64, (10, 20, 30)),
                                                              "image/png")}))
            if st_small == 201:
                created_media.append(up_small[0]["id"])
                check("小图不生成缩略图（防 sips 放大）", up_small[0].get("thumb_path") is None,
                      str(up_small[0].get("thumb_path")))

            st4, tl2 = call("GET", "/api/events?person_id=%d" % p["id"])
            hit = [x for x in (tl2 or {}).get("items", []) if x["id"] == e_img["id"]]
            check("事件列表带回 media（时间轴能显示缩略图）",
                  bool(hit) and len(hit[0].get("media") or []) == 1, str(hit)[:200])

            st5, _ = call("POST", "/api/media",
                          raw=multipart({}, {"file": ("evil.txt", b"not an image", "text/plain")}))
            check("非图片类型被拒 400", st5 == 400, "status=%s" % st5)

            call("DELETE", "/api/media/%d" % m["id"], expect=204)
            created_media.remove(m["id"])
            st6, _ = call("GET", "/media/%s" % m["thumb_path"])
            check("删媒体后文件不可取（404）", st6 == 404, "status=%s" % st6)

            # 同内容的两份：删一份不能把另一份的文件带走
            #（文件名 = 时间戳+内容哈希 → 同内容共用同一个文件；真出过事故）
            st7, up_a = call("POST", "/api/media",
                             raw=multipart({"person_id": str(p["id"])},
                                           {"file": ("dupA.png", png, "image/png")}))
            st8, up_b = call("POST", "/api/media",
                             raw=multipart({"person_id": str(p["id"])},
                                           {"file": ("dupB.png", png, "image/png")}))
            if st7 == 201 and st8 == 201:
                ia, pa = up_a[0]["id"], up_a[0]["path"]
                ib, pb = up_b[0]["id"], up_b[0]["path"]
                created_media += [ia, ib]
                check("同内容两次上传共用同一个文件（内容哈希命名）", pa == pb, "%s vs %s" % (pa, pb))
                call("DELETE", "/api/media/%d" % ia, expect=204)
                created_media.remove(ia)
                st9, left = call("GET", "/api/media?person_id=%d" % p["id"])
                row_ok = any(x["id"] == ib for x in (left or []))
                st10, _ = call("GET", "/media/%s" % pb)
                check("删掉重复那份后，另一份的行和文件都还在（不连带删文件）",
                      row_ok and st10 == 200, "行=%s 文件=%s" % (row_ok, st10))

        # --- 人物编辑（名称 / 别名 / 备注）---
        st, edited = call("PATCH", "/api/persons/%d" % p["id"], {
            "display_name": PREFIX + "伴侣改名",
            "aliases": PREFIX + "别名",
            "notes": PREFIX + "备注",
        })
        check("人物可编辑（名称/别名/备注）",
              st == 200 and (edited or {}).get("display_name") == PREFIX + "伴侣改名"
              and (edited or {}).get("notes") == PREFIX + "备注",
              "status=%s %s" % (st, str(edited)[:120]))
        call("PATCH", "/api/persons/%d" % p["id"], {"display_name": PREFIX + "伴侣"})

        # --- 圈子 / 熟悉度 / 通过谁认识 ---
        st, her_friend = call("POST", "/api/persons", {
            "display_name": PREFIX + "她的朋友", "relation_type": "friend",
            "circle": "partner", "familiarity": 2, "via_person_id": p["id"],
        })
        if st == 201:
            created_persons.append(her_friend["id"])
        check("建「她那边」的人：圈子/熟悉度/通过谁 + 默认敏感",
              st == 201 and her_friend.get("circle") == "partner"
              and her_friend.get("familiarity") == 2
              and her_friend.get("via_name") == PREFIX + "伴侣"
              and her_friend.get("sensitivity") == "sensitive",
              "status=%s %s" % (st, str(her_friend)[:180]))

        st, filtered = call("GET", "/api/persons?circle=partner")
        check("按圈子筛选人物",
              st == 200 and any(x["id"] == her_friend["id"] for x in (filtered or [])),
              "status=%s" % st)

        # --- 事件类型 ↔ 模块映射（记录页据此按人的模块开关过滤「记什么」）---
        st, cfg = call("GET", "/api/config")
        ets = {t["key"]: t.get("module") for t in (cfg or {}).get("event_types", [])}
        module_keys = {m["key"] for m in (cfg or {}).get("modules", [])}
        check("事件类型声明了对应模块（服装→outfit、生理期→cycle…）",
              st == 200 and ets.get("outfit") == "outfit" and ets.get("period") == "cycle"
              and ets.get("meeting") == "interaction" and ets.get("gift") == "gift"
              and ets.get("health") == "health" and ets.get("contact") == "contact"
              and ets.get("text") is None,
              str(ets)[:200])
        check("类型引用的模块都存在于 modules 配置（否则前端会永远隐藏）",
              all(v in module_keys for v in ets.values() if v),
              "modules=%s" % sorted(module_keys))

        st, rel = call("POST", "/api/relations", {
            "from_person_id": p["id"], "to_person_id": her_friend["id"],
            "label": PREFIX + "朋友",
        })
        if st == 201:
            created_relations.append(rel["id"])
        st2, rels = call("GET", "/api/relations?person_id=%d" % her_friend["id"])
        check("关系边可建可查（含双向人名）",
              st == 201 and any(r["id"] == rel["id"] and r["to_name"] == PREFIX + "她的朋友"
                                for r in (rels or [])),
              "status=%s %s" % (st2, str(rels)[:160]))

        # --- 服装（彻底版）：单品唯一化 + 穿搭引用 + 去重 ---
        st, it1 = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "bottom", "name": PREFIX + "黑裤", "color": "黑色"})
        check("建单品（穿 0 次）", st == 201 and it1.get("wear_count") == 0, "status=%s %s" % (st, it1))

        st, dup = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "bottom", "name": PREFIX + "黑裤", "color": "黑色"},
            expect=409)
        check("同名同类同色建不出第二条（409，结构级去重）", st == 409, "status=%s %s" % (st, str(dup)[:120]))

        st, of1 = call("POST", "/api/outfits", {
            "person_id": p["id"], "event_date": today.isoformat(),
            "items": [{"item_id": it1["id"]},
                      {"category": "top", "name": PREFIX + "白毛衣", "color": "白色"}],
            "note": PREFIX + "冒烟穿搭"})
        check("记穿搭：复用已有 + 内联新建（1 条事件 / 2 件单品）",
              st == 201 and len(of1.get("items") or []) == 2, "status=%s %s" % (st, str(of1)[:160]))
        if st == 201:
            created_events.append(of1["id"])

        st, of2 = call("POST", "/api/outfits", {
            "person_id": p["id"], "event_date": today.isoformat(),
            "items": [{"category": "top", "name": PREFIX + "白毛衣", "color": "白色"}]})
        check("再穿一次同名单品：不新建、次数累加", st == 201, "status=%s %s" % (st, str(of2)[:160]))
        if st == 201:
            created_events.append(of2["id"])

        st, allitems = call("GET", "/api/wardrobe/items?person_id=%d" % p["id"])
        by_name = {i["name"]: i["wear_count"] for i in (allitems or {}).get("items", [])}
        check("单品数 = 2（同名单品只有一条）", len(by_name) == 2, str(by_name))
        check("穿着次数正确聚合（黑裤 1 / 白毛衣 2）",
              by_name.get(PREFIX + "黑裤") == 1 and by_name.get(PREFIX + "白毛衣") == 2, str(by_name))

        st, tl3 = call("GET", "/api/events?person_id=%d&type_key=outfit" % p["id"])
        hit = [x for x in (tl3 or {}).get("items", []) if x["id"] == of1.get("id")]
        check("时间轴的穿搭事件带回 items（前端显示单品 chips）",
              bool(hit) and len(hit[0].get("items") or []) == 2, str(hit)[:200])

        st, itA = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "top", "name": PREFIX + "灰卫衣"})
        st, itB = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "top", "name": PREFIX + "卫衣外套"})
        for it in (itA, itB):
            stx, ofx = call("POST", "/api/outfits", {
                "person_id": p["id"], "event_date": today.isoformat(),
                "items": [{"item_id": it["id"]}]})
            if stx == 201:
                created_events.append(ofx["id"])
        st, mg = call("POST", "/api/wardrobe/items/%d/merge" % itB["id"], {"into_id": itA["id"]})
        check("合并单品：穿着记录改挂 + 源软删",
              st == 200 and mg.get("merged_item_id") == itB["id"] and mg.get("wear_count") == 2,
              "status=%s %s" % (st, str(mg)[:160]))
        st, detB = call("GET", "/api/wardrobe/items/%d" % itB["id"])
        check("被合并的单品仍可查（merged_into_id，可撤销）",
              st == 200 and detB.get("merged_into_id") == itA["id"], str(detB)[:160])
        st, lst = call("GET", "/api/wardrobe/items?person_id=%d" % p["id"])
        check("合并后列表不再出现作废那条",
              all(i["id"] != itB["id"] for i in (lst or {}).get("items", [])), str(lst)[:160])
        st, _ = call("DELETE", "/api/wardrobe/items/%d" % itA["id"], expect=409)
        check("有穿着记录的单品不允许直接删（409，提示合并/停用）", st == 409, "status=%s" % st)
        st, dups = call("GET", "/api/wardrobe/duplicates?person_id=%d" % p["id"])
        check("重复候选接口可用（只出候选，不自动合并）",
              st == 200 and "groups" in (dups or {}), str(dups)[:160])

        # --- 编辑（时间轴）---
        old_day = (today - dt.timedelta(days=3)).isoformat()
        st, ed = call("PATCH", "/api/events/%d" % of1["id"], {
            "title": PREFIX + "改后标题", "body": PREFIX + "改后正文",
            "tags": PREFIX + "新标签", "event_date": old_day})
        check("编辑记录字段（标题/正文/标签/日期）",
              st == 200 and ed["title"] == PREFIX + "改后标题" and ed["event_date"] == old_day,
              "status=%s %s" % (st, str(ed)[:160]))

        # 穿搭：全量替换单品（去掉白毛衣、换上一双鞋）→ 标题按单品重算（没手改时）
        st, _ = call("PATCH", "/api/events/%d" % of1["id"], {
            "items": [{"item_id": it1["id"]},
                      {"category": "shoes", "name": PREFIX + "白鞋", "color": "白色"}]})
        st2, det = call("GET", "/api/outfits/%d" % of1["id"])
        check("编辑穿搭：单品被整体替换",
              st == 200 and st2 == 200 and [i["name"] for i in det["items"]] == [PREFIX + "黑裤", PREFIX + "白鞋"],
              str(det.get("items") if isinstance(det, dict) else det)[:160])
        check("未手改标题时按单品重算",
              det.get("title") == PREFIX + "黑裤 + " + PREFIX + "白鞋", str(det.get("title")))
        counts2 = {i["name"]: i["wear_count"]
                   for i in call("GET", "/api/wardrobe/items?person_id=%d" % p["id"])[1]["items"]}
        # 白毛衣 还被 of2（第二次穿搭）引用着，所以次数应为 1 而不是 0；
        # 关键断言是「of1 不再引用它」+「新加的白鞋有 1 次」
        check("编辑穿搭后各单品次数正确（白毛衣只剩另一条穿搭的 1 次）",
              counts2.get(PREFIX + "白毛衣") == 1 and counts2.get(PREFIX + "白鞋") == 1
              and counts2.get(PREFIX + "黑裤") == 1, str(counts2))
        check("被移出的单品不再被这条穿搭引用",
              PREFIX + "白毛衣" not in [i["name"] for i in det["items"]], str(det.get("items")))

        # 相处：改日期/地点必须同步明细，否则「多久没见」与统计一直用旧日期算
        st, e_meet = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "meeting", "event_date": today.isoformat(),
            "title": PREFIX + "见面", "location": PREFIX + "A", "hours": 2, "overnight": False})
        if st == 201:
            created_events.append(e_meet["id"])
            st, _ = call("PATCH", "/api/events/%d" % e_meet["id"], {
                "event_date": old_day, "title": PREFIX + "改后见面", "location": PREFIX + "B",
                "hours": 4, "overnight": True})
            mine = [x for x in call("GET", "/api/interactions?person_id=%d" % p["id"])[1]
                    if (x.get("note") or "") == PREFIX + "改后见面"]
            check("编辑相处记录后 interactions 同步（日期/地点/过夜/时长）",
                  len(mine) == 1 and mine[0]["occurred_on"] == old_day
                  and mine[0]["location"] == PREFIX + "B" and mine[0]["overnight"] is True
                  and float(mine[0]["hours"]) == 4, str(mine)[:200])
            # 收尾：删掉这条（顺带验证删事件会把同步过的明细一起带走），
            # 否则后面的「删相处事件后无孤儿」会被它误伤
            call("DELETE", "/api/events/%d" % e_meet["id"], expect=204)
            created_events.remove(e_meet["id"])
            left = [x for x in call("GET", "/api/interactions?person_id=%d" % p["id"])[1]
                    if (x.get("note") or "") == PREFIX + "改后见面"]
            check("删掉编辑过的相处记录后明细没有孤儿", left == [], str(left)[:160])

        # 生理期：改日期同步 cycle_records；改到已占用日期要 409（不能静默失败）
        st, e_per1 = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "period", "event_date": today.isoformat(),
            "title": PREFIX + "经期"})
        st_b, e_per2 = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "period",
            "event_date": (today - dt.timedelta(days=28)).isoformat(), "title": PREFIX + "经期2"})
        if st == 201 and st_b == 201:
            created_events += [e_per1["id"], e_per2["id"]]
            st, _ = call("PATCH", "/api/events/%d" % e_per1["id"],
                         {"event_date": (today - dt.timedelta(days=1)).isoformat()})
            cyc = call("GET", "/api/cycle?person_id=%d" % p["id"])[1]
            check("编辑生理期日期同步 cycle_records",
                  st == 200 and any(c["start_date"] == (today - dt.timedelta(days=1)).isoformat()
                                    for c in cyc), str(cyc)[:160])
            st, _ = call("PATCH", "/api/events/%d" % e_per1["id"],
                         {"event_date": (today - dt.timedelta(days=28)).isoformat()}, expect=409)
            check("生理期改到已占用日期 → 409（不静默失败）", st == 409, "status=%s" % st)

        # --- 三人场合：一个事件关联多人 ---
        st, ev_multi = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text", "event_date": today.isoformat(),
            "title": PREFIX + "三人场合",
            "person_ids": [p["id"], her_friend["id"]],
        })
        check("事件可同时关联多人（三人场合）", st == 201, "status=%s %s" % (st, str(ev_multi)[:120]))
        if st == 201:
            created_events.append(ev_multi["id"])

        st, tcard = call("GET", "/api/today")
        anni = (tcard or {}).get("anniversaries")
        check("今天卡片含纪念日天数（距今天数 + 距下次）",
              st == 200 and isinstance(anni, list)
              and (not anni or (anni[0].get("days_since") is not None
                                and anni[0].get("days_to_next") is not None)),
              str(anni)[:160])

        # --- 扇出清理：删事件应带走明细 ---
        call("DELETE", "/api/events/%d" % e3["id"], expect=204)
        created_events.remove(e3["id"])
        st, inter2 = call("GET", "/api/interactions?person_id=%d" % p["id"])
        check("删相处事件后 interactions 无孤儿",
              isinstance(inter2, list) and not any(
                  PREFIX in (i.get("note") or "") for i in inter2), str(inter2))

    finally:
        # --- 清理 ---
        for rid in created_relations:
            call("DELETE", "/api/relations/%d" % rid, expect=204)
        for mid in created_media:
            call("DELETE", "/api/media/%d" % mid, expect=204)
        for eid in created_events:
            call("DELETE", "/api/events/%d" % eid, expect=204)
        for tid in created_todos:
            call("DELETE", "/api/todos/%d" % tid, expect=204)
        # 生理期扇出可能残留，逐个删
        for pid in created_persons[1:]:
            st, cyc = call("GET", "/api/cycle?person_id=%d" % pid)
            if isinstance(cyc, list):
                for c in cyc:
                    call("DELETE", "/api/cycle/%d" % c["id"], expect=204)
        for pid in reversed(created_persons):
            call("DELETE", "/api/persons/%d" % pid, expect=204)
        st, left = call("GET", "/api/persons?include_inactive=true")
        residue = [x for x in (left or []) if x.get("display_name", "").startswith(PREFIX)]
        check("清理干净（无残留测试数据）", not residue, str(residue))

        # 磁盘也不该留孤儿图片（删人要连带清掉 media 文件）
        st, storage1 = call("GET", "/api/media/storage")
        check("磁盘无残留图片文件（删人连带清理）",
              (storage1 or {}).get("files", 0) == files_before,
              "before=%s after=%s" % (files_before, (storage1 or {}).get("files")))

    print("\n== 结果：%d 通过 / %d 失败 ==" % (len(passed), len(failed)))
    if failed:
        print("失败项：" + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
