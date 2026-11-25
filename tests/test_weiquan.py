import unittest
from datetime import date

from weiquan import agent, rules


def sample():
    return ("11月18日签收的蓝牙耳机,拆开右耳没声音,客服说只能换不能退,"
            "商品页写着七天无理由,订单 1699 元。")


class TestClassify(unittest.TestCase):
    def test_no_reason(self):
        cats = rules.classify(sample())
        keys = [c["key"] for c in cats]
        self.assertIn("no_reason", keys)
        self.assertIn("three_pack", keys)

    def test_unmatched(self):
        self.assertEqual(rules.classify("今天天气不错,出门散步"), [])

    def test_quality_keyword(self):
        cats = rules.classify("收到的是假货,包装和专柜不一样")
        self.assertIn("quality", [c["key"] for c in cats])


class TestDates(unittest.TestCase):
    def test_full_date(self):
        self.assertEqual(rules.parse_date("2026-11-18 签收"), date(2026, 11, 18))

    def test_month_day(self):
        self.assertEqual(rules.parse_date("11月18日签收的", today=date(2026, 11, 25)), date(2026, 11, 18))

    def test_relative(self):
        self.assertEqual(rules.parse_date("昨天到的", today=date(2026, 11, 25)), date(2026, 11, 24))

    def test_empty(self):
        self.assertIsNone(rules.parse_date("没写日期", today=date(2026, 11, 25)))


class TestTimeline(unittest.TestCase):
    def test_remaining(self):
        cats = rules.classify(sample())
        tl = rules.timeline(date(2026, 11, 18), today=date(2026, 11, 21), cats=cats)
        no_reason = [d for d in tl["deadlines"] if d["key"] == "no_reason"][0]
        self.assertEqual(no_reason["remain"], 4)

    def test_expired(self):
        cats = rules.classify(sample())
        tl = rules.timeline(date(2026, 11, 10), today=date(2026, 11, 25), cats=cats)
        self.assertTrue(tl["expired"])
        self.assertEqual(tl["days"], 15)

    def test_no_sign(self):
        tl = rules.timeline(None, today=date(2026, 11, 25), cats=[])
        self.assertIsNone(tl["days"])

    def test_three_pack_two_nodes(self):
        cats = rules.classify(sample())
        tl = rules.timeline(date(2026, 11, 18), today=date(2026, 11, 21), cats=cats)
        names = [d["name"] for d in tl["deadlines"]]
        self.assertIn("三包·7 日退货", names)
        self.assertIn("三包·15 日换货", names)


class TestExceptionsAndPromises(unittest.TestCase):
    def test_custom_exception(self):
        ex = rules.exceptions("这是定制的杯子,刻了名字")
        self.assertTrue(any(e["name"] == "消费者定作" for e in ex))

    def test_gift_deduction(self):
        ex = rules.exceptions("退货时赠品还在,满减也想退")
        names = [e["name"] for e in ex]
        self.assertIn("赠品需一并退回", names)

    def test_promise_ten(self):
        p = rules.promises("商家页面写着假一赔十")
        self.assertEqual(p[0]["claim"], "十倍赔偿")

    def test_no_promise(self):
        self.assertEqual(rules.promises("就是普通退货"), [])


class TestEvidence(unittest.TestCase):
    def test_missing(self):
        ev = rules.evidence_check(["订单"], "")
        have = [e["key"] for e in ev["provided"]]
        self.assertIn("order", have)
        self.assertGreaterEqual(len(ev["missing"]), 5)

    def test_text_evidence(self):
        ev = rules.evidence_check([], "我有发票和保修卡")
        self.assertIn("invoice", [e["key"] for e in ev["provided"]])

    def test_empty(self):
        self.assertEqual(len(rules.evidence_check([], "")["missing"]), 8)


class TestLetters(unittest.TestCase):
    def test_platform_letter(self):
        r = rules.analyze(sample(), sign=date(2026, 11, 18), today=date(2026, 11, 21))
        letter = r["letters"]["platform"]
        self.assertIn("投诉事由", letter)
        self.assertIn("2026-11-18", letter)
        self.assertIn("第五十五条", letter)

    def test_merchant_letter(self):
        r = rules.analyze(sample(), sign=date(2026, 11, 18), today=date(2026, 11, 21))
        self.assertIn("申请售后", r["letters"]["merchant"])

    def test_letters_without_sign(self):
        r = rules.analyze("不想要了", today=date(2026, 11, 25))
        self.assertIn("投诉事由", r["letters"]["platform"])


class TestStrip(unittest.TestCase):
    def test_strip_days(self):
        s = agent.strip_numbers("你还有 3 天可以退")
        self.assertNotIn("3 天", s)
        self.assertIn("相应期限", s)

    def test_strip_money(self):
        s = agent.strip_numbers("订单 1699 元,按 30% 赔")
        self.assertNotIn("1699", s)
        self.assertNotIn("30%", s)

    def test_strip_date(self):
        self.assertNotIn("11月18日", agent.strip_numbers("11月18日签收"))


class TestPipeline(unittest.TestCase):
    def test_offline_pipeline(self):
        r = agent.handle(sample(), force_mock=True)
        self.assertEqual(r["mode"], "offline")
        self.assertTrue(r["advice"])
        self.assertTrue(r["talking_points"])
        self.assertTrue(r["risks"])
        self.assertIn("七天无理由", r["verdict"])

    def test_offline_structure_matches_model(self):
        off = agent.handle(sample(), force_mock=True)
        self.assertEqual(set(off) >= {"advice", "talking_points", "risks", "verdict"}, True)

    def test_mock_uses_exception(self):
        r = agent.handle("这是定制商品,不想要了", force_mock=True)
        self.assertTrue(any("定作" in x for x in r["risks"]))

    def test_offline_no_categories(self):
        r = agent.handle("随便聊聊", force_mock=True)
        self.assertTrue(r["advice"])
        self.assertIn("没有识别到", r["verdict"])

    def test_verdict_expired(self):
        r = agent.handle(sample(), sign=date(2026, 11, 1), force_mock=True)
        self.assertIn("已过期", r["verdict"])


if __name__ == "__main__":
    unittest.main()
