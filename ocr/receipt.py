"""Extract one payment record from the OCR lines of a phone screenshot.

Input lines come from RapidOCR: {"text": str, "score": float, "box": [[x, y] * 4]}.
The parser is deliberately rule based and screen-layout aware rather than app specific:
the headline amount is the largest amount-only text, labels sit in a left column with
their values on the same row, and the merchant is a labelled value or the line above
the headline amount.
"""
import re
from datetime import date

_FULLWIDTH = str.maketrans({
    "￥": "¥", "（": "(", "）": ")", "：": ":", "，": ",", "－": "-", "—": "-", "–": "-",
    "−": "-", "＋": "+", "．": ".", "　": " ",
})
_AMOUNT_ONLY = re.compile(
    r"^(?P<sign>[-+])?\s*(?P<cur>US\$|HK\$|\$|¥|RMB|CNY)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d+)\s*(?P<unit>元|美元|USD)?$")
_AMOUNT_IN = re.compile(r"(?P<cur>US\$|HK\$|\$|¥)?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{2})\s*(?P<unit>元|美元)?")
_DATETIME = re.compile(
    r"(?P<y>20\d{2})\s*[-/.年]\s*(?P<m>\d{1,2})\s*[-/.月]\s*(?P<d>\d{1,2})\s*日?"
    r"(?:\s*(?P<ampm>上午|下午|晚上|凌晨|中午)?\s*(?P<H>\d{1,2})\s*:\s*(?P<M>\d{2})(?:\s*:\s*(?P<S>\d{2}))?)?")

LABELS = {
    "merchant": ("收款方", "商户全称", "商户名称", "商户", "收款人", "收款账户", "对方账户", "交易对象", "转账给"),
    "detail": ("商品说明", "商品名称", "商品", "订单信息", "转账说明"),
    "method": ("付款方式", "支付方式", "付款信息"),
    "time": ("支付时间", "交易时间", "付款时间", "创建时间", "下单时间", "转账时间"),
    "amount": ("实付金额", "支付金额", "付款金额", "订单金额", "合计", "金额"),
    "category": ("账单分类", "交易分类"),
}
_ALL_LABELS = {label for group in LABELS.values() for label in group}
_INCOME = ("收款成功", "已收款", "已收钱", "退款成功", "已退款", "退款到账", "转入成功", "已存入", "收益发放")
# Money moved between one's own accounts or into investments: real outflow, but not consumption.
_TRANSFER = ("基金份额", "理财产品", "申购", "定投", "信用卡还款", "还款成功", "转入余额宝", "转入零钱通")
# Alipay labels every bill with its own category; trust it over keyword guesses.
_CATEGORY_KIND = {"投资理财": "transfer", "信用借还": "transfer", "收入": "income", "退款": "income"}
_CATEGORY_PRIMARY = {
    "餐饮美食": "吃饭", "交通出行": "交通", "爱车养车": "交通", "日用百货": "购物", "服饰装扮": "购物", "数码电器": "购物",
    "家居家装": "购物", "母婴亲子": "购物", "美容美发": "个人护理", "充值缴费": "缴费", "住房物业": "住房",
    "休闲娱乐": "娱乐", "文化休闲": "娱乐", "运动户外": "运动", "医疗健康": "医疗", "教育培训": "教育",
    "酒店旅游": "旅行", "宠物": "宠物", "生活服务": "生活服务"}
_EXPENSE = ("支付成功", "付款成功", "交易成功", "已支付", "扣款成功", "充值成功", "已付款", "支出", "订单金额",
            "购买成功", "订阅成功", "已重新订阅", "付款信息")
_NOT_MERCHANT = _INCOME + _EXPENSE + (
    "账单详情", "全部账单", "订单详细信息", "订单详情", "完成", "返回", "交易详情", "账单", "更多",
    "微信支付", "支付宝", "已重新订阅", "已订阅")
_PAYMENT_WORDS = ("付款", "支付", "余额", "合计", "总计", "金额", "实付", "优惠")
_PRIMARY_HINTS = (
    ("吃饭", ("外卖", "美团", "饿了么", "餐", "饭", "面", "粉", "食堂", "肯德基", "麦当劳", "汉堡", "火锅", "烧烤", "小吃")),
    ("饮品", ("咖啡", "瑞幸", "星巴克", "奶茶", "喜茶", "蜜雪", "茶饮", "库迪")),
    ("交通", ("滴滴", "地铁", "公交", "出行", "打车", "高德", "铁路", "12306", "航空", "加油", "停车", "单车", "骑行")),
    ("购物", ("淘宝", "天猫", "京东", "拼多多", "超市", "便利店", "商城", "盒马", "山姆")),
    ("数码订阅", ("App Store", "iTunes", "Apple", "Google", "OpenAI", "ChatGPT", "会员", "订阅")),
)


class Line:
    __slots__ = ("text", "x0", "x1", "y0", "y1")

    def __init__(self, text, box):
        self.text = " ".join(text.translate(_FULLWIDTH).split())
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def _cents(num):
    whole, _, frac = num.replace(",", "").partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def _currency(cur, unit, text=""):
    joined = f"{cur or ''}{unit or ''}{text}"
    if "US$" in joined or "美元" in joined or "USD" in joined:
        return "USD"
    if "HK$" in joined:
        return "HKD"
    if cur == "$":
        return "USD"
    return "CNY"


def _is_label(line, names=_ALL_LABELS):
    text = line.text.rstrip(":").strip()
    return text in names


def _row_value(lines, label, all_lines):
    """Text to the right of a label on the same row, plus wrapped continuation lines."""
    tolerance = max(label.h, 20) * 0.6
    row = [l for l in lines if l is not label and l.x0 > label.x1 - 5 and abs(l.cy - label.cy) < tolerance]
    if not row:
        return ""
    row.sort(key=lambda l: l.x0)
    value_x, bottom = row[0].x0, max(l.y1 for l in row)
    parts = [l.text for l in row]
    for line in sorted(all_lines, key=lambda l: l.y0):
        if line in row or line.cy <= bottom:
            continue  # boxes of wrapped lines may overlap the previous line slightly
        if abs(line.x0 - value_x) > max(label.h, 20) or any(
                abs(o.cy - line.cy) < tolerance and o.x1 < value_x for o in all_lines):
            break  # next row starts (it has its own label column)
        if line.y0 - bottom > max(label.h, 20) * 1.2:
            break
        parts.append(line.text)
        bottom = line.y1
    return " ".join(parts).rstrip(">").strip()


def _labelled(lines, group):
    for name in LABELS[group]:
        for line in lines:
            if _is_label(line, (name,)):
                value = _row_value(lines, line, lines)
                if value:
                    return value
    return ""


def _datetime(texts):
    best = None
    for text in texts:
        for m in _DATETIME.finditer(text):
            try:
                day = date(int(m["y"]), int(m["m"]), int(m["d"]))
            except ValueError:
                continue
            hour = minute = second = None
            if m["H"] is not None:
                hour, minute, second = int(m["H"]), int(m["M"]), int(m["S"] or 0)
                if m["ampm"] in ("下午", "晚上") and hour < 12:
                    hour += 12
                if m["ampm"] == "凌晨" and hour == 12:
                    hour = 0
                if hour > 23 or minute > 59 or second > 59:
                    hour = minute = second = None
            candidate = (hour is not None, day, (hour, minute, second))
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        return None, None
    _, day, (hour, minute, second) = best
    clock = f"{hour:02d}:{minute:02d}:{second:02d}" if hour is not None else None
    return day.isoformat(), clock


def _primary_hint(*texts):
    joined = " ".join(t for t in texts if t)
    for name, words in _PRIMARY_HINTS:
        if any(word.lower() in joined.lower() for word in words):
            return name
    return ""


def parse(raw_lines, height=None):
    lines = [Line(l["text"], l["box"]) for l in raw_lines if l.get("text", "").strip()]
    if not lines:
        return {"amount": None, "kind": "unknown", "confident": False, "category": "", "currency": "CNY", "date": None, "time": None,
                "merchant": "", "detail": "", "method": "", "primaryNote": "", "foreign": ""}
    height = height or max(l.y1 for l in lines)
    body = [l for l in lines if l.y0 > height * 0.045]  # drop the status bar (clock, battery)
    texts = [l.text for l in body]

    # Headline amount: the tallest line that is only an amount.
    headline, match = None, None
    for line in body:
        m = _AMOUNT_ONLY.match(line.text.replace(" ", ""))
        if not m or not (m["cur"] or "." in m["num"] or "," in m["num"] or m["sign"]):
            continue
        if headline is None or line.h > headline.h:
            headline, match = line, m
    amount = currency = sign = None
    foreign = ""
    if headline is not None:
        amount, sign = _cents(match["num"]), match["sign"]
        currency = _currency(match["cur"], match["unit"], headline.text)
    else:
        value = _labelled(body, "amount")
        m = _AMOUNT_IN.search(value)
        if m:
            amount, currency = _cents(m["num"]), _currency(m["cur"], m["unit"], value)
    if amount is not None and currency != "CNY":
        # Prefer an RMB amount shown elsewhere, e.g. "1340.83元(200.00美元)".
        for text in texts:
            for m in _AMOUNT_IN.finditer(text):
                if m["unit"] == "元" and "美元" not in text[m.start():m.end()]:
                    foreign = f"{amount / 100:.2f} {currency}"
                    amount, currency = _cents(m["num"]), "CNY"
                    break
            if currency == "CNY":
                break
        if currency != "CNY":
            foreign = f"{amount / 100:.2f} {currency}"

    joined = "\n".join(texts)
    # Evidence that this screen is a payment record rather than any text with a number in it.
    category = _labelled(body, "category")
    category_kind = _CATEGORY_KIND.get(category)
    confident = bool(category) or sign in ("-", "+") or any(k in joined for k in _INCOME + _EXPENSE + _TRANSFER)
    if sign == "+" or category_kind == "income" or (sign != "-" and any(k in joined for k in _INCOME)):
        kind = "income"
    elif category_kind == "transfer" or any(k in joined for k in _TRANSFER):
        kind = "transfer"
    elif sign == "-" or any(k in joined for k in _EXPENSE) or headline is not None:
        kind = "expense"
    else:
        kind = "unknown"

    merchant = _labelled(body, "merchant")
    if not merchant and headline is not None:
        above = [l for l in body if l.y1 <= headline.y0 + 2 and headline.y0 - l.y1 < headline.h * 1.5
                 and not _AMOUNT_ONLY.match(l.text.replace(" ", ""))]
        above.sort(key=lambda l: -l.y1)
        for line in above[:1]:
            if line.text not in _NOT_MERCHANT and not _is_label(line):
                merchant = line.text
    if not merchant and headline is not None:
        # App Store style: product name on the same row as the price. The same price may repeat
        # in a payment summary row further down, so walk every copy from the top.
        copies = sorted((l for l in body if l.text.replace(" ", "") == headline.text.replace(" ", "")),
                        key=lambda l: l.y0)
        for copy in copies:
            same_row = [l for l in body if l is not copy and abs(l.cy - copy.cy) < copy.h * 0.6
                        and not any(word in l.text for word in _PAYMENT_WORDS)]
            if same_row:
                merchant = min(same_row, key=lambda l: l.x0).text
                break
    detail = _labelled(body, "detail")
    method = _labelled(body, "method")
    labelled_time = _labelled(body, "time")
    day, clock = _datetime([labelled_time] if labelled_time else [])
    if day is None:
        pairs = texts + [a + b for a, b in zip(texts, texts[1:])]
        day, clock = _datetime(pairs)
    return {
        "amount": amount, "kind": kind, "confident": confident, "currency": currency or "CNY", "foreign": foreign,
        "date": day, "time": clock, "merchant": merchant[:60], "detail": detail[:200], "method": method[:60],
        "category": category[:30], "primaryNote": _CATEGORY_PRIMARY.get(category) or _primary_hint(merchant, detail),
    }


# Bill lists (支付宝/微信 账单, often a long screenshot): each row is a title with the amount at the
# right edge, then optional category and status lines, then the time. Month headers ("11月",
# "2025年12月") give the year for dates written as "11-05" or "11月5日".
_LIST_TIME = re.compile(r"^(?:(?P<rel>今天|昨天|前天)|(?:(?P<y>20\d{2})[-/.年])?(?P<m>\d{1,2})[-/.月](?P<d>\d{1,2})日?)"
                        r"\s*(?P<H>\d{1,2}):(?P<M>\d{2})$")
_MONTH_HEAD = re.compile(r"^(?:(?P<y>20\d{2})\s*年\s*)?(?P<m>\d{1,2})\s*月$")
_ROW_AMOUNT = re.compile(r"(?P<sign>[-+])?\s*¥?\s*(?P<num>\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})$")
# Rows that moved no money, or that a later row cancels.
_LIST_VOID = ("交易关闭", "已全额退款", "已关闭", "支付失败", "已撤销", "已取消")
_LIST_CATEGORIES = set(_CATEGORY_PRIMARY) | set(_CATEGORY_KIND) | {
    "其他", "账户存取", "转账红包", "商业服务", "公共服务", "保险", "公益", "亲友代付", "红包", "转账"}
_LIST_NOT_SPENDING = ("余额宝", "零钱通", "小荷包", "收益发放", "自动转入", "转出到余额", "基金", "理财")


def _list_day(m, ref, header):
    if m["rel"]:
        return date.fromordinal(ref.toordinal() - ("今天", "昨天", "前天").index(m["rel"]))
    month, day = int(m["m"]), int(m["d"])
    if m["y"]:
        year = int(m["y"])
    elif header and header[0] and header[1] == month:
        year = header[0]
    else:  # no year shown: the latest such date not after the screenshot
        year = ref.year if (month, day) <= (ref.month, ref.day) else ref.year - 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_list(raw_lines, width=None, today=None, include_income=False):
    """Expense rows of a bill list, or None when the screen is not a bill list.

    Returns {"entries": [fields...], "skipped": n}; each entry has the same keys as parse() plus
    "unsure" (amount shown without a minus sign) and "region" ([top, bottom, image width] of the row in pixels).
    Income and refunds are included only when include_income is enabled. Transfers between
    one's own accounts, investments, closed and fully refunded orders are counted as skipped.
    """
    lines = sorted((Line(l["text"], l["box"]) for l in raw_lines if l.get("text", "").strip()), key=lambda l: l.cy)
    if not lines:
        return None
    width = width or max(l.x1 for l in lines)
    today = today or date.today()

    anchors = []  # (line, amount match, title text from the same line)
    for line in lines:
        if line.x1 < width * 0.8:
            continue
        m = _ROW_AMOUNT.search(line.text)
        if not m:
            continue
        prefix = line.text[:m.start()].strip()
        if not prefix and line.x0 < width * 0.55:
            continue  # a total in a summary block, not a row amount
        anchors.append((line, m, prefix))

    headers = [(l, _MONTH_HEAD.match(l.text.replace(" ", ""))) for l in lines if l.x0 < width * 0.3]
    headers = [(l.cy, (int(m["y"]) if m["y"] else None, int(m["m"]))) for l, m in headers if m]

    entries, skipped = [], 0
    for index, (anchor, m, prefix) in enumerate(anchors):
        top = anchor.y0
        bottom = anchors[index + 1][0].y0 if index + 1 < len(anchors) else anchor.y1 + anchor.h * 6
        tolerance = anchor.h * 0.6
        title = prefix or " ".join(
            l.text for l in lines if l is not anchor and abs(l.cy - anchor.cy) < tolerance
            and l.x0 > width * 0.12 and l.x1 < anchor.x0)
        below = [l for l in lines if anchor.cy + tolerance < l.cy < bottom - tolerance * 0.5]
        when = category = status = None
        for line in below:
            if when is None and (t := _LIST_TIME.match(line.text)):
                when = t
            elif line.x0 > width * 0.55:
                status = status or line.text
            elif category is None and line.text in _LIST_CATEGORIES:
                category = line.text
        if when is None:
            continue  # not a bill row
        header = max((h for h in headers if h[0] < anchor.cy), default=(0, None))[1]
        day = _list_day(when, today, header)
        amount, sign = _cents(m["num"]), m["sign"]
        title = title.rstrip(".…").strip()
        joined = f"{title} {status or ''}"
        income = sign == "+" or title.startswith("退款") or _CATEGORY_KIND.get(category or "") == "income" or any(word in title for word in _INCOME)
        if (amount == 0 or any(word in joined for word in _LIST_VOID)
                or category == "账户存取" or _CATEGORY_KIND.get(category or "") == "transfer"
                or any(word in title for word in _LIST_NOT_SPENDING + _TRANSFER)
                or (income and not include_income)):
            skipped += 1
            continue
        hour, minute = int(when["H"]), int(when["M"])
        entries.append({
            "amount": amount, "kind": "income" if income else "expense", "confident": True, "currency": "CNY", "foreign": "",
            "date": day.isoformat() if day else None,
            "time": f"{hour:02d}:{minute:02d}:00" if hour < 24 and minute < 60 else None,
            "merchant": title[:60], "detail": "", "method": "", "category": (category or "")[:30],
            "primaryNote": _CATEGORY_PRIMARY.get(category or "") or _primary_hint(title),
            # Without a minus sign the row may not be a completed payment (e.g. 待收货, 闲鱼 担保交易).
            "unsure": (not income and sign != "-") or any(word in title for word in ("转账", "红包")),
            "region": [int(top - anchor.h * 0.6), int(bottom), int(width)],
        })
    if len(entries) + skipped < 2:
        return None
    return {"entries": entries, "skipped": skipped}


if __name__ == "__main__":
    import json
    import sys
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(json.dumps(parse_list(data["lines"]) or parse(data["lines"]), ensure_ascii=False, indent=2))
