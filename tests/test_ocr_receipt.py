"""Field extraction from OCR lines. Layouts mirror real 1206-1440 px wide phone screenshots;
names, amounts and card numbers are made up."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ocr"))
from datetime import date  # noqa: E402

from receipt import parse, parse_list  # noqa: E402


def L(text, x0, y0, x1, y1):
    return {"text": text, "score": 0.99, "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


ALIPAY_FOREIGN = [
    L("10:19", 106, 60, 335, 132), L("51", 1050, 52, 1121, 136),
    L("<", 41, 214, 96, 292), L("账单详情", 479, 214, 719, 288), L("全部账单", 948, 210, 1161, 285),
    L("Example Pay Inc", 430, 531, 770, 590),
    L("-688.88", 375, 611, 826, 741),
    L("交易成功", 496, 748, 705, 823),
    L("订单金额", 64, 897, 257, 962), L("688.88元(100.00美元)", 370, 897, 822, 958),
    L("汇率", 64, 997, 174, 1065), L("1美元 = 6.8888人民币", 370, 1000, 814, 1061),
    L("支付时间", 64, 1100, 253, 1164), L("2026-11-1017:32:03", 370, 1104, 787, 1164),
    L("付款方式", 64, 1197, 253, 1271), L("示例银行储蓄卡(1234)>", 370, 1207, 839, 1268),
    L("商品说明", 68, 1304, 249, 1367), L("App Store & iTunes US – Gift", 370, 1311, 1109, 1371),
    L("Card", 361, 1366, 487, 1444),
    L("支付奖励", 68, 1474, 253, 1539), L("立即领取16积分", 376, 1485, 749, 1546),
    L("账单分类", 61, 1930, 257, 2006), L("其他>", 975, 1930, 1141, 2006),
    L("备注", 64, 2464, 178, 2540), L("添加>", 975, 2464, 1137, 2540),
]

WECHAT_SUCCESS = [
    L("23:41", 49, 38, 184, 104), L("5G 87%", 1182, 30, 1362, 104),
    L("支付成功", 557, 417, 877, 520),
    L("￥23.50", 470, 620, 970, 800),
    L("收款方", 120, 900, 270, 960), L("兰州牛肉面（中关村店）", 600, 900, 1130, 960),
    L("支付方式", 120, 1000, 320, 1060), L("零钱", 600, 1000, 700, 1060),
    L("完成", 664, 2700, 776, 2770),
]

APP_STORE = [
    L("14:38", 115, 60, 330, 130),
    L("订单详细信息", 450, 270, 750, 330),
    L("Example Pro Plan", 276, 505, 687, 560), L("US$19.99", 820, 505, 1090, 560),
    L("已重新订阅", 276, 595, 495, 655), L("Example User", 276, 680, 545, 735),
    L("2026年11月9日下午9:", 276, 760, 740, 815), L("05", 276, 845, 322, 900),
    L("付款信息账户余额", 108, 1040, 505, 1100), L("US$19.99", 820, 1040, 1090, 1100),
    L("订单日期", 108, 1265, 280, 1320), L("订单号", 618, 1265, 750, 1320),
]

ALIPAY_INCOME = [
    L("账单详情", 479, 214, 719, 288),
    L("张三", 540, 531, 660, 590),
    L("+500.00", 400, 611, 800, 741),
    L("交易成功", 496, 748, 705, 823),
    L("创建时间", 64, 1100, 253, 1164), L("2026-11-08 09:01:22", 370, 1104, 787, 1164),
]


ALIPAY_FUND = [
    L("17:18", 120, 60, 300, 130), L("账单详情", 479, 214, 719, 288),
    L("示例基金销售有限公司", 300, 531, 900, 590), L("250.00", 400, 611, 800, 741),
    L("付款成功,基金份额确认中", 360, 748, 840, 823),
    L("创建时间", 64, 1100, 253, 1164), L("2026-11-13 09:29:04", 370, 1104, 787, 1164),
    L("账单分类", 61, 1930, 257, 2006), L("投资理财 >", 900, 1930, 1141, 2006),
]

ALIPAY_YIELD = [
    L("账单详情", 479, 214, 719, 288), L("示例货币基金A>", 400, 531, 800, 590),
    L("0.01", 520, 611, 680, 741), L("交易成功", 496, 748, 705, 823),
    L("商品说明", 68, 1304, 249, 1367), L("余额宝-2026.11.09-收益发放", 370, 1311, 900, 1371),
    L("账单分类", 61, 1930, 257, 2006), L("投资理财 >", 900, 1930, 1141, 2006),
]

ALIPAY_MEAL = [
    L("账单详情", 479, 214, 719, 288), L("示例拉面馆", 480, 531, 720, 590),
    L("-17.00", 420, 611, 780, 741), L("交易成功", 496, 748, 705, 823),
    L("账单分类", 61, 1930, 257, 2006), L("餐饮美食 >", 900, 1930, 1141, 2006),
]


def row(y, title, amount, category=None, when="11-05 13:21", status=None, icon=None, merged=False):
    """One row of the Alipay bill list (1440 px wide), starting at y."""
    lines = [L(f"{title} {amount}", 243, y, 1360, y + 70)] if merged else [L(title, 243, y, 900, y + 70), L(amount, 1150, y, 1360, y + 70)]
    if icon:
        lines.append(L(icon, 82, y + 10, 213, y + 95))
    if category:
        lines.append(L(category, 243, y + 95, 445, y + 165))
    if status:
        lines.append(L(status, 1070, y + 95, 1357, y + 160))
    lines.append(L(when, 243, y + 190, 490, y + 250))
    return lines


ALIPAY_LIST = [
    L("21:42", 85, 40, 307, 110), L("全部", 78, 360, 217, 445), L("支出", 303, 360, 445, 445),
    L("11月", 69, 540, 375, 700), L("支出", 94, 700, 217, 780), L("￥1,234.56", 85, 770, 375, 860),
    L("收入", 577, 700, 693, 780), L("￥12.34", 570, 770, 791, 860),
    *row(1100, "示例牛肉面外卖订单", "-20.10", "餐饮美食", "今天13:04", icon="闪购"),
    *row(1490, "余额宝-收益发放", "0.09", "投资理财", "今天05:32"),
    *row(1880, "示例黄金ETF联接C-买入", "100.00", "投资理财", "今天09:37", status="付款成功,基金份额确认中"),
    *row(2270, "示例超市", "-5.99", "日用百货", "昨天 23:16", status="自动扣款成功"),
    *row(2660, "示例手机壳", "-0.00", "数码电器", "昨天14:47", icon="淘"),
    *row(3050, "示例汉堡(新区店)外卖...", "-15.00", "餐饮美食", "11-07 17:24", merged=True),
    *row(3440, "小荷包-转出到余额", "+13.65", "账户存取", "11-07 16:29"),
    *row(3830, "示例舵机一套", "80.80", "日用百货", "11-06 13:27", icon="闲鱼"),
    *row(4220, "退款-示例牛肉外卖订单", "22.90", "退款", "11-05 18:48"),
    *row(4610, "示例牛肉外卖订单", "-22.90", "餐饮美食", "11-05 18:39", status="已全额退款"),
    *row(5000, "示例石锅饭", "15.00", "餐饮美食", "11-05 13:20", status="交易关闭"),
    L("2025年12月", 69, 5400, 500, 5560),
    *row(5700, "示例咖啡", "-3.00", "餐饮美食", "12-31 08:05"),
]


class ReceiptTest(unittest.TestCase):
    def test_bill_list_keeps_only_spending(self):
        result = parse_list(ALIPAY_LIST, 1440, date(2026, 11, 13))
        rows = [(e["date"], e["time"], e["amount"], e["merchant"], e["primaryNote"], e["unsure"]) for e in result["entries"]]
        self.assertEqual(rows, [
            ("2026-11-13", "13:04:00", 2010, "示例牛肉面外卖订单", "吃饭", False),
            ("2026-11-12", "23:16:00", 599, "示例超市", "购物", False),
            ("2026-11-07", "17:24:00", 1500, "示例汉堡(新区店)外卖", "吃饭", False),
            ("2026-11-06", "13:27:00", 8080, "示例舵机一套", "购物", True),
            ("2025-12-31", "08:05:00", 300, "示例咖啡", "吃饭", False),
        ])
        # yield, fund purchase, 0.00 order, 小荷包 transfer, refund, refunded order, closed order
        self.assertEqual(result["skipped"], 7)
        top, bottom, width = result["entries"][0]["region"]
        self.assertTrue(top < 1100 and 1300 < bottom <= 1490 and width == 1440)

    def test_income_in_bill_list_requires_opt_in(self):
        sample = [*row(100, "工资", "+3000.00", "收入", "今天13:04"),
                  *row(500, "超市", "-20.00", "日用百货", "今天14:04")]
        old = parse_list(sample, 1440, date(2026, 11, 13))
        new = parse_list(sample, 1440, date(2026, 11, 13), include_income=True)
        self.assertEqual([e['kind'] for e in old['entries']], ['expense'])
        self.assertEqual([e['kind'] for e in new['entries']], ['income', 'expense'])
        self.assertEqual(new['entries'][0]['amount'], 300000)

    def test_single_bills_are_not_lists(self):
        for screen in (ALIPAY_FOREIGN, WECHAT_SUCCESS, APP_STORE, ALIPAY_FUND, ALIPAY_MEAL, []):
            self.assertIsNone(parse_list(screen))

    def test_fund_purchase_is_a_transfer(self):
        r = parse(ALIPAY_FUND, height=2622)
        self.assertEqual((r["amount"], r["kind"], r["category"]), (25000, "transfer", "投资理财"))
        self.assertTrue(r["confident"])

    def test_yield_payout_is_income(self):
        r = parse(ALIPAY_YIELD, height=2622)
        self.assertEqual((r["amount"], r["kind"]), (1, "income"))

    def test_alipay_category_suggests_primary_note(self):
        r = parse(ALIPAY_MEAL, height=2622)
        self.assertEqual((r["kind"], r["primaryNote"]), ("expense", "吃饭"))

    def test_alipay_bill_with_foreign_currency(self):
        r = parse(ALIPAY_FOREIGN, height=2622)
        self.assertEqual(r["amount"], 68888)
        self.assertEqual((r["kind"], r["currency"]), ("expense", "CNY"))
        self.assertEqual((r["date"], r["time"]), ("2026-11-10", "17:32:03"))
        self.assertEqual(r["merchant"], "Example Pay Inc")
        self.assertEqual(r["detail"], "App Store & iTunes US - Gift Card")
        self.assertEqual(r["method"], "示例银行储蓄卡(1234)")
        self.assertEqual(r["primaryNote"], "数码订阅")

    def test_wechat_success_page(self):
        r = parse(WECHAT_SUCCESS, height=3200)
        self.assertEqual((r["amount"], r["kind"]), (2350, "expense"))
        self.assertEqual(r["merchant"], "兰州牛肉面(中关村店)")
        self.assertEqual(r["method"], "零钱")
        self.assertIsNone(r["date"])  # success pages carry no date; the phone uses the screenshot time
        self.assertEqual(r["primaryNote"], "吃饭")
        self.assertTrue(r["confident"])

    def test_bare_number_is_not_confident(self):
        r = parse([L("聊天", 500, 200, 640, 260), L("23.50", 300, 900, 520, 980)], height=3200)
        self.assertEqual(r["amount"], 2350)
        self.assertFalse(r["confident"])

    def test_app_store_receipt_in_dollars(self):
        r = parse(APP_STORE, height=2622)
        self.assertEqual((r["amount"], r["currency"], r["foreign"]), (1999, "USD", "19.99 USD"))
        self.assertEqual((r["date"], r["time"]), ("2026-11-09", "21:05:00"))
        self.assertEqual(r["merchant"], "Example Pro Plan")

    def test_income_is_not_an_expense(self):
        r = parse(ALIPAY_INCOME, height=2622)
        self.assertEqual((r["amount"], r["kind"]), (50000, "income"))
        self.assertEqual(r["date"], "2026-11-08")

    def test_empty_screen(self):
        r = parse([], height=100)
        self.assertIsNone(r["amount"])
        self.assertEqual(r["kind"], "unknown")


if __name__ == "__main__":
    unittest.main()
