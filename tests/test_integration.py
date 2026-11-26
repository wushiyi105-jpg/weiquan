"""集成测试:真起 HTTP 服务、真接一个假模型服务、真跑 CLI 子进程。

test_weiquan.py 只测纯函数;这里断言的是「请求 → 报告」整条链路,
以及模型层接得通、数字与期限守卫真的把模型写的东西挡在门外。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from weiquan import agent, llm, web
from weiquan import db as dbmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = "买了个蓝牙耳机,11月21日签收,右耳没声音,不想要了,商品页写着七天无理由退货"
SIGN = "2026-11-21"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestHTTPServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db = dbmod.Database(os.path.join(self.tmp.name, "weiquan.db"))
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), web._handler(db, {"api_key": None}, True))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def _post(self, payload: dict):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/check" % self.port,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_post_check_timeline(self):
        code, r = self._post({"text": TEXT, "sign": SIGN, "evidence": "订单,商品页"})
        self.assertEqual(code, 200)
        self.assertEqual(r["mode"], "offline")
        self.assertEqual(r["timeline"]["sign"], SIGN)
        self.assertEqual(r["timeline"]["days"], (date.today() - date(2026, 11, 21)).days)
        self.assertTrue(r["categories"])
        self.assertIn("platform", r["letters"])
        self.assertIn("merchant", r["letters"])
        self.assertTrue(r["saved_id"])

    def test_post_future_sign_400(self):
        code, r = self._post({"text": TEXT, "sign": "2026-12-31"})
        self.assertEqual(code, 400)
        self.assertIn("晚于今天", r["error"])


class FakeLLM(BaseHTTPRequestHandler):
    """假的 OpenAI 兼容服务:返回带天数与金额的建议,验证守卫会剥掉。"""

    advice = []
    calls = 0

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).calls += 1
        content = {"advice": self.advice,
                   "talking_points": ["按页面承诺处理,今天内回复我处理方案"],
                   "risks": ["商家以已拆封为由拒绝,要求出具检测报告"]}
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)},
                                           "finish_reason": "stop"}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class TestModelLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.cfg = {"api_key": "test-key", "base_url": "http://127.0.0.1:%d" % cls.port,
                   "model": "fake-model"}

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def test_model_connects_and_numbers_are_stripped(self):
        FakeLLM.advice = ["还剩 3 天,立刻申请退货", "把聊天记录和商品页截图保存"]
        before = FakeLLM.calls
        r = agent.handle(TEXT, sign=date(2026, 11, 21), config=self.cfg)
        self.assertEqual(r["mode"], "model")
        self.assertEqual(FakeLLM.calls - before, 1)
        self.assertIn("相应期限", r["advice"][0])
        self.assertNotIn("3 天", r["advice"][0])
        self.assertEqual(r["advice"][1], "把聊天记录和商品页截图保存")
        self.assertIn("今天内回复", r["talking_points"][0])

    def test_days_and_money_stripped(self):
        FakeLLM.advice = ["按 1500 元的方案赔偿,7 个工作日内到账", "先找平台介入"]
        r = agent.handle(TEXT, sign=date(2026, 11, 21), config=self.cfg)
        self.assertNotIn("1500", r["advice"][0])
        self.assertNotIn("7 个工作日", r["advice"][0])
        self.assertEqual(r["timeline"]["days"], (date.today() - date(2026, 11, 21)).days)

    def test_llm_error_is_reported(self):
        cfg = dict(self.cfg, base_url="http://127.0.0.1:%d" % free_port())
        with self.assertRaises(llm.LLMError):
            llm.chat([{"role": "user", "content": "hi"}], config=cfg, retries=0, timeout=3)


class TestCLI(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, "-m", "weiquan", *args],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_check_end_to_end(self):
        p = self._run("--mock", "check", "--text", TEXT, "--sign", SIGN,
                      "--evidence", "订单,商品页,聊天记录")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("七天无理由退货", p.stdout)
        self.assertIn("签收日 2026-11-21", p.stdout)
        self.assertIn("剩", p.stdout)

    def test_check_file_vector(self):
        path = os.path.join(ROOT, "_tmp_case.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEXT)
        try:
            p = self._run("--mock", "check", "--file", path, "--sign", SIGN)
        finally:
            os.unlink(path)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("签收日 2026-11-21", p.stdout)

    def test_future_sign_exit_2(self):
        p = self._run("--mock", "check", "--text", TEXT, "--sign", "2026-12-31")
        self.assertEqual(p.returncode, 2)
        self.assertIn("晚于今天", p.stderr)


if __name__ == "__main__":
    unittest.main()
