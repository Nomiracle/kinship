#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""农历（中国阴阳历）工具 —— 自包含、无第三方依赖。

表数据：1900–2099 每个农历年的「闰月月序 + 各月大小（29/30 天）」，
由天文历法数据生成，可用 scripts/../ 的生成脚本重算（见文件末尾注释）。

用法：
    from lunar_cn import solar_to_lunar, lunar_to_solar, format_lunar, ganzhi_year
    lunar = solar_to_lunar(datetime.date(2026, 9, 29))   # (2026, 8, 19, False)
    date  = lunar_to_solar(2026, 9, 29)                  # 农历九月廿九 -> 公历
"""

import datetime

# 1900 年正月初一 = 公历 1900-01-31
_BASE = datetime.date(1900, 1, 31)
_START_YEAR = 1900

# 每项："<闰月序(base36 字符，0=无闰月)><12 或 13 位月长，0=29天 1=30天>"
# 月序按农历年内的实际顺序排列，闰月紧跟其同名月之后。
_TABLE = [
    "8010010110110100100101011100101001010111501010010011010110100100110",
    "0110110010101401101010101010010101101010010011010110120100101011101",
    "0010010101110610100100110110101001001101011010010010151101010100101",
    "0101101010100011010110101021001011011010010010101101170100100110111",
    "001001001011101010010010115101100100101100110101001010011011010100",
    "4101011011010100010101101100100101010111201001001011110010010010111",
    "6011001001011001101010010100111010100101501101011010010010110101101",
    "0001010110110310010011011100100100101110711001001011010110010010101",
    "0110101001010611011010010100101101010101001010110101041010101011011",
    "0001001011101010010010110121100100101011010101001010171011010010101",
    "001101100101001011010101015010101011010100100110110100101001011101",
    "3010100101011100101001010118101010010101001110100101010011010101010",
    "6101011010101001010101101010010010110110410100101011100101001010111",
    "0010100100110311101001001100110110010101701011010101010010101101010",
    "0100101101101501001010111010010010101101010100100110141101001001101",
    "0110100100101811010101001010101101010100010110101101061001011011010",
    "01001010110110010010011011410100100101110101001001011a1011001001011",
    "001101010010100110110101006101011011010001010101101100100101010111",
    "5010010010111100100100101110011001001011301101010010100111010100101",
    "8011010110010100101101011000101010110110510010011011010100100101110",
    "0110010010110411010100101010110101001010011011010010120101101010101",
    "0010101101010710101010110110001001011101010010010110151100100101011",
    "0101010010101010110100101041011010101010010101101010190101010110101",
    "001001011101001010010110116010100101011100101001010110101010010011",
    "4011101001010100110101010100101011010101201001101101010010010110110",
    "6101001010111001010010011100110100100110511101001001100110101010011",
    "0010110101010301101011010100100101101101b01001010111010010010101101",
    "0101001001101611010010010110110100100101011010101001051101101010100",
    "0101101011010001010110110120100101011011001001001101171010010010111",
    "010100100101101010101001015101101010010100110110100100101011011010",
    "3010101011011001001001101118010010010111100100100101110011001001011",
    "6011010100101001110101001010011010101010410101011011000101010101110",
    "0100100101110311001001011100110010010110711010100101010110101001010",
    "0110110100101501011010101010010101101010010100110110140101001011101",
    "0010100101101810101001010110101010010101010110100101061011010101010",
    "010101101010100101010110104101001011101001010010110110010100101011",
    "3101010010011100110100100117011100101001100110101010100101011010101",
    "5010011011010100100101101100101001010111401010010011100110100010110",
    "8111010010011001101010100100110110101010601101011010100010101101101",
    "0010010101110410100100111010101000101101011010001010121101100100101",
]


def _parse_table():
    """紧凑表是「各年分片拼接」的长字符串：解析成 [(leap_month, [月长...]), ...] 并算出每年正月初一偏移。"""
    data = "".join(_TABLE)
    years, offsets = [], []
    total = 0
    i = 0
    while i < len(data):
        leap = int(data[i], 36)
        i += 1
        n = 13 if leap else 12
        chunk = data[i:i + n]
        assert len(chunk) == n, chunk
        i += n
        lens = [29 + int(c) for c in chunk]
        years.append((leap, lens))
        offsets.append(total)
        total += sum(lens)
    offsets.append(total)
    assert len(years) == 200, len(years)
    return years, offsets, total


_YEARS, _OFFSETS, _TOTAL_DAYS = _parse_table()

_CN_NUM = "一二三四五六七八九十"
_DAY_NAMES = (
    ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十"]
    + ["十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
    + ["廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]
)
_MONTH_NAMES = ["正月", "二月", "三月", "四月", "五月", "六月",
                "七月", "八月", "九月", "十月", "冬月", "腊月"]
_GAN = "甲乙丙丁戊己庚辛壬癸"
_ZHI = "子丑寅卯辰巳午未申酉戌亥"
_ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"


def solar_to_lunar(d):
    """公历 date -> (农历年, 月, 日, 是否闰月)。范围 1900-01-31 ~ 2099 年农历年末。"""
    days = (datetime.date(d.year, d.month, d.day) - _BASE).days
    if days < 0 or days >= _TOTAL_DAYS:
        raise ValueError("日期超出表范围（1900-01-31 ~ 2099 农历年末）")
    lo, hi = 0, len(_YEARS) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _OFFSETS[mid] <= days:
            lo = mid
        else:
            hi = mid - 1
    year = _START_YEAR + lo
    rem = days - _OFFSETS[lo]
    leap_month, lens = _YEARS[lo]
    month = 0
    for i, ln in enumerate(lens):
        if rem < ln:
            month = i + 1
            break
        rem -= ln
    # 把「农历年内的第几个月」还原成（月序, 是否闰月）
    is_leap = False
    if leap_month:
        if month == leap_month + 1:
            month_no, is_leap = leap_month, True
        elif month > leap_month + 1:
            month_no = month - 1
        else:
            month_no = month
    else:
        month_no = month
    return year, month_no, rem + 1, is_leap


def lunar_to_solar(year, month, day, is_leap=False):
    """(农历年, 月, 日, 是否闰月) -> 公历 date。"""
    idx = year - _START_YEAR
    if not 0 <= idx < len(_YEARS):
        raise ValueError("农历年超出表范围 [1900, 2099]")
    leap_month, lens = _YEARS[idx]
    if not 1 <= month <= 12:
        raise ValueError("月份超出范围")
    if is_leap and leap_month != month:
        raise ValueError("%d 年没有闰%d月" % (year, month))
    days = _OFFSETS[idx]
    for i, ln in enumerate(lens):
        pos_month = i + 1
        is_leap_pos = bool(leap_month) and pos_month == leap_month + 1
        month_no = leap_month if is_leap_pos else (pos_month - 1 if leap_month and pos_month > leap_month + 1 else pos_month)
        if month_no == month and is_leap_pos == is_leap:
            if not 1 <= day <= ln:
                raise ValueError("日超出范围（该月 %d 天）" % ln)
            return _BASE + datetime.timedelta(days=days + day - 1)
        days += ln
    raise ValueError("月份超出范围")


def lunar_month_name(month, is_leap=False):
    return ("闰" if is_leap else "") + _MONTH_NAMES[month - 1]


def lunar_day_name(day):
    return _DAY_NAMES[day - 1]


def ganzhi_year(year):
    """农历年 -> (干支, 生肖)，如 ('丙午', '马')。"""
    return _GAN[(year - 4) % 10] + _ZHI[(year - 4) % 12], _ZODIAC[(year - 4) % 12]


def format_lunar(d):
    """公历 date -> '丙午年（马）八月十九' 形式的中文农历字符串。"""
    y, m, d_, leap = solar_to_lunar(d)
    gz, zodiac = ganzhi_year(y)
    return "%s年（%s）%s%s" % (gz, zodiac, lunar_month_name(m, leap), lunar_day_name(d_))


def lunar_date_for_solar_year(year, month, day, is_leap=False):
    """给「农历月日」，求它在某个公历年内的公历日期。

    农历年与公历年在这里按「农历年 == year」处理；农历九月廿九这种日期只可能出现
    一次，取该农历年内的对应公历日。返回 date 或 None（该年无此日期，如闰月不存在）。
    """
    try:
        return lunar_to_solar(year, month, day, is_leap)
    except ValueError:
        return None


def next_lunar_occurrence(month, day, today, is_leap=False):
    """从 today 起（含今天）最近一次「农历 month/day」对应公历日 -> (date, 农历年)。"""
    for y in (today.year, today.year + 1, today.year + 2):
        d = lunar_date_for_solar_year(y, month, day, is_leap)
        if d and d >= today:
            return d, y
    return None, None


def next_lunar_occurrences(month, day, today, count=3):
    """连续 count 次「农历 month/day」的公历日期（含今年可能已过的下一次）。"""
    out, y = [], today.year
    while len(out) < count and y <= 2099:
        d = lunar_date_for_solar_year(y, month, day)
        if d and d >= today:
            out.append((d, y))
        y += 1
    return out


# 表数据生成方式（一次性，需要 lunardate 或等价历法库）：
#   对 1900–2099 每年取「闰月月序」与「12/13 个月的长度」，拼成上面的紧凑字符串。
#   本文件的表由天文历法数据生成，并与独立实现（python-lunardate）逐日穷举比对通过。

if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:] or [datetime.date.today().isoformat()]:
        y, m, d = (int(x) for x in arg.split("-"))
        dt = datetime.date(y, m, d)
        print("%s -> %s" % (dt, format_lunar(dt)))
