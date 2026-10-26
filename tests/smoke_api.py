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


def heic_bytes(width: int, height: int, rgb: tuple = (200, 120, 60)):
    """合成一张 HEIC（iPhone 直传格式）；本环境没有 pillow-heif 时返回 None。

    仓库红线：不引入真实照片，素材一律现场合成。
    """
    try:
        import io

        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        buf = io.BytesIO()
        Image.new("RGB", (width, height), rgb).save(buf, format="HEIF")
        return buf.getvalue()
    except Exception:
        return None

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
            "gender": "female", "birthday": "1990-01-01", "birthday_lunar": False,
        })
        check("建 partner 人物（女）", st == 201 and p.get("gender") == "female",
              "status=%s %s" % (st, p))
        created_persons.append(p["id"])

        st, mods = call("GET", "/api/persons/%d/modules" % p["id"])
        check("伴侣 + 女 → 自动获得默认模块（含 cycle）",
              "cycle" in (mods or {}).get("enabled", []), str(mods))

        # --- 性别决定生理期模块：男性不展示也开不了；未知不自动开但可手动开 ---
        st, male = call("POST", "/api/persons", {
            "display_name": PREFIX + "男伴侣", "relation_type": "partner", "gender": "male",
        })
        if st == 201:
            created_persons.append(male["id"])
        st_m, mods_m = call("GET", "/api/persons/%d/modules" % male["id"])
        check("男性：默认不开 cycle，且 available 里没有（开关都不展示）",
              st == 201 and "cycle" not in (mods_m or {}).get("enabled", [])
              and "cycle" not in (mods_m or {}).get("available", []),
              str(mods_m))
        st_m2, forced = call("PUT", "/api/persons/%d/modules" % male["id"],
                             {"modules": ["cycle", "interaction"]})
        check("男性：PUT 强开 cycle 被忽略（不报错也不生效）",
              st_m2 == 200 and "cycle" not in (forced or {}).get("enabled", []),
              str(forced))

        st, unknown = call("POST", "/api/persons", {
            "display_name": PREFIX + "性别未知", "relation_type": "partner",
        })
        if st == 201:
            created_persons.append(unknown["id"])
        st_u, mods_u = call("GET", "/api/persons/%d/modules" % unknown["id"])
        check("性别未知：不自动开 cycle，但 available 里有（可手动开）",
              st == 201 and "cycle" not in (mods_u or {}).get("enabled", [])
              and "cycle" in (mods_u or {}).get("available", []),
              str(mods_u))
        st_u2, opened = call("PUT", "/api/persons/%d/modules" % unknown["id"],
                             {"modules": ["interaction", "cycle"]})
        check("性别未知：手动开 cycle 能生效",
              st_u2 == 200 and "cycle" in (opened or {}).get("enabled", []), str(opened))

        st, patched = call("PATCH", "/api/persons/%d" % unknown["id"], {"gender": "male"})
        check("性别可通过 PATCH 修改",
              st == 200 and (patched or {}).get("gender") == "male",
              "status=%s %s" % (st, str(patched)[:120]))

        # --- 生日：明确写法 + 倒计时必须同时给（只有天数会被误读成别的倒计时）---
        st, listed = call("GET", "/api/persons")
        me = next((x for x in (listed or []) if x["id"] == p["id"]), None)
        check("人物列表同时给出「生日的明确写法 + 还有几天 + 满几岁」",
              st == 200 and me is not None
              and me.get("birthday_text") == "1990-01-01"
              and me.get("birthday_next") == "2027-01-01"
              and me.get("birthday_days_left") == (dt.date(2027, 1, 1) - today).days,
              str(me)[:200] if me else "没找到这个人")

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

        # 跨日相处：一条记录表达「周五去、周日回」，过夜与时长由后端派生
        # 故意放在最近：让「距上次见面」能区分「按开始日算」和「按结束日算」
        span_start = (today - dt.timedelta(days=2)).isoformat()
        span_end = (today - dt.timedelta(days=1)).isoformat()
        st, e_span = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "meeting",
            "event_date": span_start, "ended_on": span_end,
            "title": PREFIX + "跨日相处", "location": PREFIX + "某地", "hours": 3,
        })
        check("建跨日相处记录", st == 201 and (e_span.get("meeting") or {}).get("ended_on") == span_end,
              "status=%s %s" % (st, str(e_span)[:200]))
        if st == 201:
            created_events.append(e_span["id"])
            m = e_span.get("meeting") or {}
            check("跨日相处派生：2 天 1 晚、过夜为真、hours 丢弃",
                  m.get("span_days") == 2 and m.get("span_nights") == 1
                  and m.get("overnight") is True and m.get("hours") is None, str(m)[:200])
            st, tl_span = call("GET", "/api/events?person_id=%d" % p["id"])
            hit = [x for x in (tl_span.get("items") or []) if x.get("id") == e_span["id"]]
            check("列表里相处事件自带 meeting 块",
                  st == 200 and hit and (hit[0].get("meeting") or {}).get("span_nights") == 1,
                  str(hit)[:200])
            # 改开始日把跨度改成负数 → 400，不能静默写坏明细
            st_bad_span, _ = call("PATCH", "/api/events/%d" % e_span["id"],
                                  {"event_date": (today + dt.timedelta(days=1)).isoformat()},
                                  expect=400)
            check("相处跨度改成负数被拒（400）", st_bad_span == 400, "status=%s" % st_bad_span)
            # 「多久没见」按跨度末日算：这段相处刚结束，不该算成 10 天没见
            st, td_span = call("GET", "/api/today?person_id=%d" % p["id"])
            me = [x for x in (td_span.get("persons") or []) if x.get("id") == p["id"]]
            check("距上次见面按结束日算（last_seen=跨度末日）",
                  st == 200 and me and me[0].get("last_seen") == span_end, str(me)[:200])
            # 用完就删：下面「删相处事件后无孤儿」是拿 PREFIX 全量扫的，
            # 留着这条跨日记录会让那条断言看起来像失败（实际是另一条测试数据还在）
            call("DELETE", "/api/events/%d" % e_span["id"], expect=204)
            created_events.remove(e_span["id"])
            st, inter_span = call("GET", "/api/interactions?person_id=%d" % p["id"])
            check("删跨日相处事件后明细也跟着走",
                  st == 200 and not any((i.get("note") or "") == PREFIX + "跨日相处"
                                        for i in (inter_span or [])), str(inter_span)[:200])

        # --- 时间轴 / 今天 / 搜索 ---
        st, tl = call("GET", "/api/events?person_id=%d" % p["id"])
        check("时间轴返回三类记录",
              st == 200 and tl.get("total", 0) >= 3, str(tl)[:200])

        st, td = call("GET", "/api/today?person_id=%d" % p["id"])
        check("今天卡片含农历与本人",
              st == 200 and td.get("lunar") and td.get("persons"), str(td)[:200])

        # 检索统一走 LIKE（ngram 索引已退役：MariaDB 没有那个 parser）。
        # 断言守的性质是「多字/单字都搜得到」，不是「走了哪个索引」——
        # 后者是实现细节，换数据库就不成立，别把它当安全断言守着。
        st, s1 = call("GET", "/api/search?q=%s" % urllib.parse.quote(PREFIX + "棕色"))
        check("多字搜索命中（LIKE）",
              st == 200 and s1.get("mode") == "like" and s1.get("items"), str(s1)[:200])

        st, s2 = call("GET", "/api/search?q=%s" % urllib.parse.quote("棕"))
        check("单字搜索命中（LIKE）",
              st == 200 and s2.get("mode") == "like" and s2.get("items"), str(s2)[:200])

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
                check("小图不生成缩略图（防放大）", up_small[0].get("thumb_path") is None,
                      str(up_small[0].get("thumb_path")))

            # HEIC 直传（iPhone 默认格式）→ 服务端必须转成 JPG。
            # 这条守的是「任何平台上都看得到图」：sips 时代这能力只在 macOS 存在，
            # 换到 Linux 会**静默失效**（原图直接进库，安卓/Chrome 破图），所以真测一遍。
            # 故意不挂 event_id：本用例只查转码，别去动上面那条「事件带回 1 张 media」的断言。
            heic = heic_bytes(400, 300)
            if heic is None:
                print("  ~ 跳过：HEIC 转码断言（本环境没装 pillow-heif）")
            else:
                st_h, up_h = call("POST", "/api/media",
                                  raw=multipart({"person_id": str(p["id"])},
                                                {"file": ("IMG_0001.heic", heic, "image/heic")}))
                ok_jpg = st_h == 201 and up_h and str(up_h[0].get("path", "")).lower().endswith(".jpg")
                check("HEIC 上传被转码成 JPG", ok_jpg, "status=%s %s" % (st_h, up_h))
                if st_h == 201:
                    created_media.append(up_h[0]["id"])
                    check("HEIC 原图保留（source_path 指向 .heic）",
                          str(up_h[0].get("source_path", "")).lower().endswith(".heic"),
                          str(up_h[0].get("source_path")))
                    st_h2, _ = call("GET", "/media/%s" % up_h[0]["path"])
                    check("转码后的 JPG 可取（200）", st_h2 == 200, "status=%s" % st_h2)

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
            # 注意：同一张图 + **同一归属** 现在会被去重成一行（上传幂等，见下一条），
            # 所以这里故意用两个不同归属（只挂人 / 挂人+事件）来构造「两份共用一份文件」。
            st7, up_a = call("POST", "/api/media",
                             raw=multipart({"person_id": str(p["id"])},
                                           {"file": ("dupA.png", png, "image/png")}))
            st8, up_b = call("POST", "/api/media",
                             raw=multipart({"person_id": str(p["id"]), "event_id": str(e_img["id"])},
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

            # 上传幂等：同一张图重复传给**同一个归属**（同一事件 / 同一单品）→ 复用同一行。
            # 不这么做的话，一次连点就会在相册里留下 N 张一模一样的图（真发生过）。
            st_d1, up_d1 = call("POST", "/api/media",
                                raw=multipart({"person_id": str(p["id"]),
                                               "event_id": str(e_img["id"])},
                                              {"file": ("same1.png", png, "image/png")}))
            st_d2, up_d2 = call("POST", "/api/media",
                                raw=multipart({"person_id": str(p["id"]),
                                               "event_id": str(e_img["id"])},
                                              {"file": ("same2.png", png, "image/png")}))
            if st_d1 == 201 and st_d2 == 201:
                created_media.append(up_d1[0]["id"])
                _, ev_media = call("GET", "/api/media?event_id=%d" % e_img["id"])
                same = [x for x in (ev_media or []) if x["path"] == up_d1[0]["path"]]
                check("同归属重复上传只留一行（上传幂等，复用同一 media 行）",
                      up_d1[0]["id"] == up_d2[0]["id"] and len(same) == 1,
                      "ids=%s/%s 同 path 行数=%d" % (up_d1[0]["id"], up_d2[0]["id"], len(same)))

        # --- 时间轴编辑面板的图片语义：给**已有**记录补图 / 删记录要连带清盘 ---
        # 后端一直支持「上传时带 event_id」，但编辑面板此前根本没有入口（图加不进去）。
        st_s0, s0 = call("GET", "/api/media/storage")
        base_files = (s0 or {}).get("files", 0)
        st_e, e_diary = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text", "event_date": today.isoformat(),
            "title": PREFIX + "带图日记",
        })
        if st_e == 201:
            created_events.append(e_diary["id"])
            st_u, up_ev = call("POST", "/api/media",
                               raw=multipart({"person_id": str(p["id"]),
                                              "event_id": str(e_diary["id"]),
                                              "captured_on": today.isoformat()},
                                             {"file": ("diary.png", png_bytes(900, 600, (200, 30, 30)),
                                                       "image/png")}))
            st_tl, tl3 = call("GET", "/api/events?person_id=%d" % p["id"])
            hit3 = [x for x in (tl3 or {}).get("items", []) if x["id"] == e_diary["id"]]
            check("编辑场景：给已有记录补图 → 事件列表带回该图（时间轴能显示）",
                  st_u == 201 and bool(hit3) and len(hit3[0].get("media") or []) == 1,
                  "upload=%s %s" % (st_u, str(hit3)[:200]))

            call("DELETE", "/api/events/%d" % e_diary["id"], expect=204)
            created_events.remove(e_diary["id"])
            st_s1, s1 = call("GET", "/api/media/storage")
            check("删记录连带清磁盘（不留孤儿图片文件）",
                  (s1 or {}).get("files", 0) == base_files,
                  "before=%s with=%s after=%s" % (base_files, (s0 or {}).get("files"),
                                                   (s1 or {}).get("files")))

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
        rec = {t["key"]: t.get("recordable", True) for t in (cfg or {}).get("event_types", [])}
        # 服装现在也能在通用「记录页」新建：记录页用弹层选择器勾单品，保存走 POST /api/outfits
        # （recordable=false 的语义留给将来别的类型）
        check("服装可在通用记录页新建（recordable 不再为 false；仍是合法 type_key）",
              rec.get("outfit") is True and rec.get("text") is True and rec.get("period") is True,
              str(rec)[:200])

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
        # 同一组「谁 —称谓→ 谁」有唯一键：重复提交必须给人话 409，不能漏成 500
        st_dup, dup = call("POST", "/api/relations", {
            "from_person_id": p["id"], "to_person_id": her_friend["id"],
            "label": PREFIX + "朋友",
        }, expect=409)
        check("重复的关系边返回 409（不是 500）",
              st_dup == 409 and bool((dup or {}).get("detail")),
              "status=%s %s" % (st_dup, str(dup)[:160]))

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

        # 多单品照片：图挂在「事件」上 → 一件全身照只存一份，单品的穿着历史里带出来
        st_ph, ph = call("POST", "/api/media",
                         raw=multipart({"person_id": str(p["id"]), "event_id": str(of1["id"])},
                                       {"file": ("outfit.png", png_bytes(900, 1200, (30, 40, 50)),
                                                 "image/png")}))
        st_one, one = call("GET", "/api/wardrobe/items/%d" % it1["id"])
        if st_ph == 201:
            created_media.append(ph[0]["id"])
        w_rows = [w for w in ((one or {}).get("wears") or []) if w.get("event_id") == of1["id"]]
        check("单品的穿着历史带出那次穿搭的照片（图挂事件、多单品共享一份）",
              st_ph == 201 and bool(w_rows) and len(w_rows[0].get("media") or []) == 1,
              "上传=%s wears=%s" % (st_ph, str(w_rows)[:160]))

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

        # --- 单品状态：卖掉 → 换新（状态/原因/日期/加入时间/替换关系/历史）---
        st, necklace = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "accessory",
            "name": PREFIX + "金项链", "color": "金色"})
        check("新单品默认「在役」，并带加入时间（本地墙钟，不是 UTC）",
              st == 201 and necklace.get("status") == "in_use"
              and necklace.get("status_label") == "在役"
              and bool(necklace.get("added_at")) and necklace.get("added_on") == today.isoformat(),
              "status=%s %s" % (st, str(necklace)[:200]))

        st, _ = call("PATCH", "/api/wardrobe/items/%d" % necklace["id"],
                     {"status": "sold"}, expect=400)
        check("改成已卖出但不写原因 → 400（离手状态原因必填）", st == 400, "status=%s" % st)
        st, _ = call("PATCH", "/api/wardrobe/items/%d" % necklace["id"],
                     {"status": "broke"}, expect=422)
        check("未知状态被拒（422）", st == 422, "status=%s" % st)

        sold_reason = PREFIX + "闲鱼卖掉，换了新项链和戒指"
        st, sold = call("PATCH", "/api/wardrobe/items/%d" % necklace["id"], {
            "status": "sold", "status_reason": sold_reason,
            "status_changed_on": today.isoformat()})
        hist = (sold or {}).get("status_history") or []
        check("改状态写原因 + 生效日期，并追加历史（不覆盖）",
              st == 200 and sold.get("status") == "sold"
              and sold.get("status_label") == "已卖出"
              and sold.get("status_reason") == sold_reason
              and len(hist) == 2 and hist[0]["status"] == "sold" and hist[-1]["status"] == "in_use",
              "status=%s %s" % (st, str(sold)[:240]))

        st, hand_list = call("GET", "/api/wardrobe/items?person_id=%d" % p["id"])
        check("已卖出的单品默认不出现在衣橱列表",
              all(i["id"] != necklace["id"] for i in (hand_list or {}).get("items", [])),
              str([i["name"] for i in (hand_list or {}).get("items", [])])[:160])
        st, off_list = call("GET", "/api/wardrobe/items?person_id=%d&include_offhand=true&status=sold" % p["id"])
        check("include_offhand + status=sold 能查到已卖掉的那条",
              st == 200 and any(i["id"] == necklace["id"] for i in (off_list or {}).get("items", [])),
              str(off_list)[:160])

        st, new_necklace = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "accessory",
            "name": PREFIX + "金项链", "color": "金色"})
        check("卖掉后同名同色可以再建（唯一键含状态，不是 500）",
              st == 201 and new_necklace["id"] != necklace["id"],
              "status=%s %s" % (st, str(new_necklace)[:160]))
        st, new_ring = call("POST", "/api/wardrobe/items", {
            "person_id": p["id"], "category": "accessory",
            "name": PREFIX + "金戒指", "color": "金色",
            "replaces_item_id": necklace["id"]})
        check("新件建的时候就能标「替代了旧件」",
              st == 201 and (new_ring.get("replaces") or {}).get("id") == necklace["id"],
              "status=%s %s" % (st, str(new_ring)[:180]))
        st, neck_again = call("PATCH", "/api/wardrobe/items/%d" % new_necklace["id"],
                              {"replaces_item_id": necklace["id"]})
        check("「替代了」也能事后补（PATCH）",
              st == 200 and (neck_again.get("replaces") or {}).get("id") == necklace["id"],
              "status=%s %s" % (st, str(neck_again)[:180]))

        st, old_det = call("GET", "/api/wardrobe/items/%d" % necklace["id"])
        repl = {x["id"] for x in (old_det or {}).get("replaced_by") or []}
        check("旧件详情反向显示「被谁替代」（1 旧 → N 新）",
              repl == {new_necklace["id"], new_ring["id"]}, str(old_det.get("replaced_by"))[:200])

        st, other_item = call("POST", "/api/wardrobe/items", {
            "person_id": her_friend["id"], "category": "accessory",
            "name": PREFIX + "别人的项链", "color": "银色"})
        st, _ = call("PATCH", "/api/wardrobe/items/%d" % new_ring["id"],
                     {"replaces_item_id": other_item["id"]}, expect=400)
        check("替换关系不能跨人（400）", st == 400, "status=%s" % st)
        st, _ = call("PATCH", "/api/wardrobe/items/%d" % new_ring["id"],
                     {"replaces_item_id": new_ring["id"]}, expect=400)
        check("不能替代自己（400）", st == 400, "status=%s" % st)

        st, _ = call("PATCH", "/api/wardrobe/items/%d" % necklace["id"],
                     {"status": "in_use", "status_reason": PREFIX + "又赎回来了"}, expect=409)
        check("改回在役但同名同色已有一件在役 → 409（不会撞唯一键变成 500）",
              st == 409, "status=%s" % st)
        st, back = call("PATCH", "/api/wardrobe/items/%d" % necklace["id"],
                        {"status": "lost", "status_reason": PREFIX + "又弄丢了"})
        check("状态可以再改（历史累计，不重置）",
              st == 200 and back.get("status") == "lost" and len(back.get("status_history") or []) == 3,
              "status=%s %s" % (st, str(back)[:200]))

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

        # 记录页的「手改标题/正文」开关：POST /api/outfits 也要认（单品是真源，手改优先）
        # （放在上面的次数断言之后：这两条会再引用黑裤，别把「次数」那条搅浑）
        st, of3 = call("POST", "/api/outfits", {
            "person_id": p["id"], "event_date": today.isoformat(),
            "items": [{"item_id": it1["id"]}],
            "title": PREFIX + "手改标题", "body": PREFIX + "手改正文"})
        check("建穿搭可带手改标题/正文（手改优先）",
              st == 201 and of3.get("title") == PREFIX + "手改标题"
              and of3.get("body") == PREFIX + "手改正文",
              "status=%s %s" % (st, str(of3)[:160]))
        if st == 201:
            created_events.append(of3["id"])
        st, of4 = call("POST", "/api/outfits", {
            "person_id": p["id"], "event_date": today.isoformat(),
            "items": [{"item_id": it1["id"]}]})
        check("不给标题/正文时仍按单品自动渲染（默认行为不变）",
              st == 201 and PREFIX + "黑裤" in (of4.get("title") or ""), str(of4)[:160])
        if st == 201:
            created_events.append(of4["id"])

        # 记录页「刚记的」排序：order=created 按写入时间（记到过去某天也得排在最前）
        old_written_day = (today - dt.timedelta(days=30)).isoformat()
        st_old, e_old = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text", "event_date": old_written_day,
            "title": PREFIX + "很久以前但刚写入"})
        if st_old == 201:
            created_events.append(e_old["id"])
        st_c, by_created = call("GET", "/api/events?person_id=%d&limit=5&order=created" % p["id"])
        st_d, by_date = call("GET", "/api/events?person_id=%d&limit=5" % p["id"])
        first_created = ((by_created or {}).get("items") or [{}])[0]
        first_date = ((by_date or {}).get("items") or [{}])[0]
        check("order=created：按写入时间排（刚写入的旧日期记录排第一）",
              st_c == 200 and first_created.get("id") == e_old["id"],
              "status=%s %s" % (st_c, str(by_created)[:200]))
        check("默认仍按事件日期排（时间轴语义不变）",
              st_d == 200 and first_date.get("id") != e_old["id"],
              "status=%s %s" % (st_d, str(first_date)[:160]))
        st_bad, _ = call("GET", "/api/events?order=bogus", expect=422)
        check("order 只接受 date/created（其余 422，不静默忽略）", st_bad == 422, "status=%s" % st_bad)

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

        # --- 易孕期 / 相对安全期参考（挂在生理期里，不另开模块）---
        st, pred2 = call("GET", "/api/cycle/prediction?person_id=%d" % p["id"])
        fert = (pred2 or {}).get("fertility") or {}
        fw = fert.get("fertile_window") or []
        check("易孕期参考可算（排卵日 + 窗口 + 规律性）",
              st == 200 and fert.get("ovulation") and len(fw) == 2
              and (fert.get("regularity") or {}).get("text")
              and isinstance(fert.get("safe_windows"), list),
              str(fert)[:220])
        if len(fw) == 2 and fert.get("ovulation"):
            check("易孕窗口 = 排卵日后 1 天结束 / 排卵日前 5 天开始",
                  (dt.date.fromisoformat(fw[1]) - dt.date.fromisoformat(fert["ovulation"])).days == 1
                  and (dt.date.fromisoformat(fert["ovulation"]) - dt.date.fromisoformat(fw[0])).days == 5,
                  "窗口=%s 排卵=%s" % (fw, fert.get("ovulation")))
        check("免责话术在位（不可用于避孕）",
              "避孕" in ((pred2 or {}).get("fertility_note") or ""),
              str((pred2 or {}).get("fertility_note"))[:140])

        st, pred_m = call("GET", "/api/cycle/prediction?person_id=%d" % male["id"])
        check("没有经期记录的人：预测不报错、易孕期为空",
              st == 200 and (pred_m or {}).get("count") == 0
              and (pred_m or {}).get("fertility") is None, str(pred_m)[:160])

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

        st, tcard_pass = call("GET", "/api/today?person_id=%d" % p["id"])
        ent = ((tcard_pass or {}).get("persons") or [{}])[0]
        check("今天卡片的人物行同时给出「生日的明确写法 + 还有几天 + 满几岁」",
              st == 200 and ent.get("birthday_text") == "1990-01-01"
              and ent.get("birthday_next") == "2027-01-01"
              and ent.get("birthday_days_left") is not None
              and ent.get("birthday_lunar") is False
              and ent.get("gender") == "female",
              str(ent)[:220])

        st, tcard_none = call("GET", "/api/today?person_id=%d" % male["id"])
        ent_none = ((tcard_none or {}).get("persons") or [{}])[0]
        check("没生日的人：生日字段为 null（不是报错、也不是别的倒计时）",
              st == 200 and ent_none.get("birthday_text") is None
              and ent_none.get("birthday_days_left") is None, str(ent_none)[:200])

        st, tcard_male = call("GET", "/api/today?person_id=%d" % male["id"])
        males = (tcard_male or {}).get("persons") or [{}]
        check("男性人物行不带生理期预测（不出现无标签的「约 N 天后」）",
              st == 200 and "cycle" not in males[0], str(males[0])[:200])

        # --- 事件时刻精确到秒（DATETIME）+ 时间轴按日分组 ---
        # 原来 event_date 是 DATE（只到日），同一天发生的事分不出先后；
        # ★ 口径：时间部分 00:00:00 = 「只记到日」，出参 event_time 为 None。
        st, e_sec = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text", "event_date": today.isoformat(),
            "event_time": "14:03:21", "title": PREFIX + "带时刻",
        })
        check("写入：日期 + 独立时刻字段 → 读回秒级 event_time/event_at",
              st == 201 and e_sec.get("event_time") == "14:03:21"
              and (e_sec.get("event_at") or "").endswith("14:03:21"), str(e_sec)[:220])
        created_events.append(e_sec["id"])
        check("写入：event_date 仍是 'YYYY-MM-DD'（老前端/老断言兼容）",
              e_sec.get("event_date") == today.isoformat(), str(e_sec.get("event_date")))

        st, e_iso = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "text",
            "event_date": today.isoformat() + "T09:15:00", "title": PREFIX + "ISO串",
        })
        check("写入：ISO 时刻串（T 分隔）也能精确到秒",
              st == 201 and e_iso.get("event_time") == "09:15:00", str(e_iso)[:220])
        created_events.append(e_iso["id"])

        st, patched = call("PATCH", "/api/events/%d" % e_sec["id"], {
            "event_date": today.isoformat(), "event_time": "23:59:59"})
        check("编辑：把时刻改到 23:59:59（日期不动）",
              st == 200 and patched.get("event_time") == "23:59:59", str(patched)[:220])
        st, cleared = call("PATCH", "/api/events/%d" % e_sec["id"],
                           {"event_date": today.isoformat()})
        check("编辑：只给日期 → 回到「只记到日」（event_time=None）",
              st == 200 and cleared.get("event_time") is None, str(cleared)[:220])
        st, _ = call("PATCH", "/api/events/%d" % e_sec["id"], {"event_time": "14:00"}, expect=422)
        check("编辑：只给时刻不给日期 → 422（不静默猜日期）", st == 422, "status=%s" % st)

        st, day_all = call("GET", "/api/events?person_id=%d&group=day&limit=200" % p["id"])
        day_list = (day_all or {}).get("days") or []
        flat = (day_all or {}).get("items") or []
        dates = [d["date"] for d in day_list]
        check("group=day：days 覆盖全部 items、按日期倒序、组内条数正确",
              st == 200 and dates == sorted(dates, reverse=True)
              and sum(d["count"] for d in day_list) == len(flat)
              and all(d["count"] == len(d["items"]) for d in day_list), str(day_all)[:220])

        st, pad = call("GET", "/api/events?person_id=%d&group=day&limit=1" % p["id"])
        pad_items = (pad or {}).get("items") or []
        pad_day = ((pad or {}).get("days") or [{}])[0].get("date")
        check("group=day：被 limit 截断的那一天补全取回（同一天不被撕成两页）",
              st == 200 and len(pad_items) >= 2
              and all(i["event_date"] == pad_day for i in pad_items), str(pad)[:220])
        check("group=day：next_offset/has_more 用补全后的条数（分页不跳记录）",
              pad.get("next_offset") == len(pad_items)
              and pad.get("has_more") == (pad.get("total", 0) > len(pad_items)),
              "next=%s has_more=%s total=%s shown=%s"
              % (pad.get("next_offset"), pad.get("has_more"), pad.get("total"), len(pad_items)))
        times = [(x.get("event_time") or "") for x in pad_items]
        timed = [t for t in times if t]
        check("group=day：同一天内有时刻的按时刻倒序、无时刻的落末尾",
              times[len(timed):] == [""] * (len(times) - len(timed))
              and timed == sorted(timed, reverse=True), str(times))

        # --- 扇出仍按「日」：明细表是 DATE 列 ---
        per_day = (today - dt.timedelta(days=100)).isoformat()
        st, e_per = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "period", "event_date": per_day,
            "event_time": "08:30:00", "title": PREFIX + "带时刻经期",
        })
        created_events.append(e_per["id"])
        st, cyc2 = call("GET", "/api/cycle?person_id=%d" % p["id"])
        check("扇出：带时刻的生理期事件 → cycle_records.start_date 取「日」",
              st == 200 and any(c.get("start_date") == per_day for c in (cyc2 or [])),
              str(cyc2)[:220])

        meet_day = (today - dt.timedelta(days=7)).isoformat()
        st, e_meet = call("POST", "/api/events", {
            "person_id": p["id"], "type_key": "meeting", "event_date": meet_day,
            "event_time": "19:00:00", "title": PREFIX + "带时刻见面",
            "location": PREFIX + "测试地",
        })
        created_events.append(e_meet["id"])
        st, inter3 = call("GET", "/api/interactions?person_id=%d" % p["id"])
        check("扇出：带时刻的相处事件 → interactions.occurred_on 取「日」",
              st == 200 and any(r.get("occurred_on") == meet_day for r in (inter3 or [])),
              str(inter3)[:220])
        # 用完就删：下面的「删事件不留孤儿明细」是拿 PREFIX 全量扫的，
        # 留着这条会让那条断言看起来像失败（实际是另一条测试数据还在）
        call("DELETE", "/api/events/%d" % e_meet["id"], expect=204)
        created_events.remove(e_meet["id"])
        st, inter4 = call("GET", "/api/interactions?person_id=%d" % p["id"])
        check("扇出：删掉这条带时刻的相处事件后，明细也跟着走",
              st == 200 and not any(r.get("occurred_on") == meet_day for r in (inter4 or [])),
              str(inter4)[:220])

        wear_day = (today - dt.timedelta(days=5)).isoformat()
        st, o_time = call("POST", "/api/outfits", {
            "person_id": p["id"], "event_date": wear_day, "event_time": "07:10:00",
            "items": [{"category": "top", "name": PREFIX + "带时刻上衣"}],
        })
        check("穿搭：写入可带时刻", st == 201 and o_time.get("event_time") == "07:10:00",
              str(o_time)[:220])
        created_events.append(o_time["id"])
        st, witem = call("GET", "/api/wardrobe/items/%d" % o_time["items"][0]["item_id"])
        wears = (witem or {}).get("wears") or [{}]
        check("穿搭：first/last_worn_on 是「日」（DATETIME 上取 .date()）",
              st == 200 and witem.get("first_worn_on") == wear_day
              and witem.get("last_worn_on") == wear_day, str(witem)[:220])
        check("穿搭：穿着历史带时刻（衣橱详情也看得到几点穿的）",
              wears[0].get("event_time") == "07:10:00", str(wears)[:220])

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
