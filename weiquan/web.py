"""Web 入口:零依赖 http.server,单页 + JSON API。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, llm, rules
from . import db as dbmod

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>维权 · 消费纠纷助手</title>
<style>
  :root{--bg:#f7f5f2;--card:#fff;--ink:#26221d;--muted:#7a7267;--brown:#8a4b2a;--soft:#f2e4d8;
        --line:#e7e0d8;--red:#b3402f;--green:#3f7d58;--radius:16px}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
  .wrap{max-width:940px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:26px;margin:0 0 4px} header p{color:var(--muted);margin:0 0 22px}
  .badge{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--soft);color:var(--brown);margin-left:8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(38,34,29,.05)}
  label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
  textarea,input{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px;font-family:inherit;background:#fff}
  textarea{line-height:1.7}
  textarea:focus,input:focus{outline:none;border-color:var(--brown);box-shadow:0 0 0 3px var(--soft)}
  .row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:170px}
  button{background:var(--brown);color:#fff;border:none;padding:12px 22px;border-radius:12px;font-size:15px;cursor:pointer}
  button:hover{filter:brightness(1.1)}
  .hint{color:var(--muted);font-size:12px;margin-top:8px}
  .spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result{display:none}.result.show{display:block}
  h3{font-size:15px;color:var(--muted);margin:20px 0 8px}
  .tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:6px;background:var(--soft);color:var(--brown);margin-right:6px}
  .ok{color:var(--green)}.bad{color:var(--red)}
  .box{background:#faf7f4;border-radius:10px;padding:12px 14px;margin:8px 0;font-size:14px;white-space:pre-wrap;line-height:1.7}
  .item{border-left:3px solid var(--brown);padding:4px 0 4px 12px;margin:10px 0;font-size:14px}
  ul{margin:6px 0 0 18px;padding:0}li{margin:6px 0;font-size:14px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>维权 · 消费纠纷助手<span class="badge" id="badge">…</span></h1>
    <p>把售后经过说清楚,算清时效、挑对路径、补齐证据,再给你两份能直接发的文字。</p>
  </header>
  <div class="card">
    <label>纠纷经过(原话即可)</label>
    <textarea id="text" rows="8" placeholder="11月18日签收的耳机,拆开发现右耳没声音,客服说只能换不能退,页面写着七天无理由,订单 1699 元"></textarea>
    <div class="row" style="margin-top:12px">
      <div><label>签收日期(可选,留空从文字里找)</label><input id="sign" placeholder="2026-11-18"></div>
      <div><label>已有证据(逗号分隔)</label><input id="ev" placeholder="订单,签收,商品页,聊天"></div>
    </div>
    <div style="margin-top:16px"><button id="btn">开始分析</button></div>
    <div class="hint">时效、例外、证据与两份文书都在本地生成;模型只写主张顺序与话术,天数日期不会被模型改写。</div>
  </div>
  <div class="result" id="res"></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function load(btn,on){btn.disabled=on;if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.innerHTML='<span class="spin"></span>';}else{btn.innerHTML=btn.dataset.label||btn.textContent;}}
$('#btn').onclick=async()=>{
  const el=$('#res');el.classList.remove('show');load($('#btn'),true);
  try{
    const p=await fetch('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#text').value,sign:$('#sign').value,evidence:$('#ev').value})});
    const r=await p.json(); if(r.error) throw new Error(r.error);
    let h='<div class="card"><div class="hint">'+(r.mode==='model'?'模型已连接':'离线模式')+(r.saved_id?' · 已入库 #'+r.saved_id:'')+'</div>';
    h+='<p style="line-height:1.75;font-size:16px">'+esc(r.verdict)+'</p>';
    h+='<h3>识别到的类目</h3>';
    if(r.categories.length){r.categories.forEach(c=>{h+='<div class="item"><b>'+esc(c.name)+'</b> <span class="tag">'+esc(c.basis)+'</span><ul>';
      c.rights.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul></div>';});}
    else{h+='<div class="hint">未识别,补一句争议原话</div>';}
    h+='<h3>时效</h3>';
    if(r.timeline.sign){h+='<div>签收 '+r.timeline.sign+' · 今天第 '+r.timeline.days+' 天</div>';}
    r.deadlines.forEach(n=>{const bad=n.indexOf('超期')>=0;h+='<div class="'+(bad?'bad':'ok')+'">'+esc(n)+'</div>';});
    if(r.exceptions.length){h+='<h3>例外与扣减</h3>';r.exceptions.forEach(e=>h+='<div class="item"><b>['+esc(e.type)+']</b> '+esc(e.name)+':'+esc(e.why)+'</div>');}
    if(r.promises.length){h+='<h3>商家承诺</h3>';r.promises.forEach(p=>h+='<div class="item"><b>'+esc(p.claim)+'</b> 原话「'+esc(p.quote)+'」<div class="hint">'+esc(p.limit)+'</div></div>');}
    h+='<h3>证据体检</h3>';
    r.evidence.provided.forEach(e=>h+='<div class="ok">✅ '+esc(e.name)+'</div>');
    r.evidence.missing.forEach(e=>h+='<div class="bad">❌ '+esc(e.name)+' —— '+esc(e.why)+'</div>');
    if(r.advice.length){h+='<h3>主张顺序</h3>';r.advice.forEach((a,i)=>h+='<div>'+(i+1)+'. '+esc(a)+'</div>');}
    if(r.talking_points.length){h+='<h3>可以直接发的话</h3>';r.talking_points.forEach(t=>h+='<div class="box">'+esc(t)+'</div>');}
    if(r.risks.length){h+='<h3>可能被拒的理由</h3><ul>';r.risks.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul>';}
    h+='<h3>给商家的第一段</h3><div class="box">'+esc(r.letters.merchant)+'</div>';
    h+='<h3>12315 / 平台投诉正文</h3><div class="box">'+esc(r.letters.platform)+'</div>';
    h+='</div>'; el.innerHTML=h;
  }catch(e){el.innerHTML='<div class="card" style="color:#b3402f">请求失败:'+esc(e.message)+'</div>';}
  el.classList.add('show');load($('#btn'),false);
};
fetch('/api/status').then(r=>r.json()).then(s=>{const b=$('#badge');
  if(s.mock){b.textContent='离线模式';b.style.background='#fee2e2';b.style.color='#b3402f';}
  else{b.textContent=s.model||'模型已连接';b.style.background='#dcfce7';b.style.color='#3f7d58';}
}).catch(()=>{});
</script>
</body></html>
"""


def _handler(db, cfg, force_mock):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock = force_mock or not cfg.get("api_key")
                self._json({"mock": mock, "model": None if mock else cfg.get("model")})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/check":
                self._json({"error": "not found"}, 404)
                return
            try:
                body = self._read()
                ev = [x.strip() for x in str(body.get("evidence") or "").split(",") if x.strip()]
                sign = rules.parse_date(body.get("sign")) if body.get("sign") else None
                r = agent.handle(body.get("text", ""), sign=sign, evidence=ev,
                                 config=cfg, db=db, force_mock=force_mock, save=True)
                self._json(r)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, db_path=None, force_mock=False):
    db = dbmod.Database(db_path)
    cfg = llm.default_config()
    httpd = ThreadingHTTPServer((host, port), _handler(db, cfg, force_mock))
    mode = "离线模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else "模型:%s" % cfg.get("model")
    print("⚖️  维权已启动:http://%s:%s  [%s]" % (host, port, mode))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
