import os
import sys
import base64
import subprocess
import tempfile
import threading
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
_lock = threading.Lock()

# Shared state - sab users yahi dekh te hain
STATE = {
    "user": None,
    "filename": None,
    "code": "",
    "output": "",
    "base64": "",
    "version": 0,
}

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lyra Hub</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: radial-gradient(circle at 50% 0%, #1a1f3a 0%, #0a0e27 60%);
  color: #e0e0e0; min-height: 100vh; padding: 20px;
}
.container { max-width: 900px; margin: 0 auto; }
.logo { text-align: center; margin-bottom: 8px; }
.logo h1 {
  font-size: 44px;
  background: linear-gradient(135deg, #00d4ff, #ff00e5, #00d4ff);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
  letter-spacing: 6px; font-weight: 800;
}
.tag { text-align: center; color: #4a5070; font-size: 12px; letter-spacing: 3px;
       text-transform: uppercase; margin-bottom: 30px; }
.card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(0,212,255,0.15);
  border-radius: 12px; padding: 25px; margin-bottom: 18px;
  backdrop-filter: blur(10px);
}
h3 { color: #00d4ff; margin-bottom: 14px; font-size: 13px;
     text-transform: uppercase; letter-spacing: 2px; font-weight: 600; }
label { display: block; margin-bottom: 8px; color: #8090b0;
        font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
input, textarea {
  width: 100%; background: rgba(0,0,0,0.4);
  border: 1px solid rgba(0,212,255,0.25);
  border-radius: 8px; padding: 12px 14px; color: #e0e0e0;
  font-size: 14px; font-family: 'JetBrains Mono', 'Courier New', monospace;
  transition: all 0.2s;
}
input:focus, textarea:focus {
  outline: none; border-color: #00d4ff;
  box-shadow: 0 0 15px rgba(0,212,255,0.25);
}
textarea { min-height: 240px; resize: vertical; line-height: 1.5; }
button {
  background: linear-gradient(135deg, #00d4ff, #ff00e5);
  color: white; border: none; padding: 12px 26px;
  border-radius: 8px; cursor: pointer; font-size: 13px;
  font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
  transition: all 0.2s;
}
button:hover:not(:disabled) { transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(0,212,255,0.4); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.secondary { background: rgba(255,255,255,0.08); color: #8090b0; }
.output-box, .b64-box {
  background: #000; border: 1px solid rgba(0,212,255,0.2);
  border-radius: 8px; padding: 14px;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 13px; white-space: pre-wrap; word-break: break-all;
  max-height: 280px; overflow-y: auto; color: #00ff88; line-height: 1.5;
}
.b64-box { color: #ff66e5; }
.hint { color: #4a5070; font-size: 11px; margin-top: 6px; }
.row { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
.status { text-align: center; margin-bottom: 18px; color: #8090b0;
          font-size: 13px; letter-spacing: 1px; }
.status b { color: #00d4ff; }
</style>
</head>
<body>
<div class="container">
  <div class="logo"><h1>LYRA HUB</h1></div>
  <div class="tag">Shared Python Playground</div>
  <div class="status" id="status"></div>
  <div id="app"></div>
</div>
<script>
var app = document.getElementById('app');
var statusEl = document.getElementById('status');
var currentStep = null;
var lastVersion = -1;
var codeDirty = false;

async function getState() {
  var r = await fetch('/state');
  return await r.json();
}
async function post(url, data) {
  var r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {})
  });
  return await r.json();
}
function escapeHtml(t) {
  return String(t == null ? '' : t).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function stepOf(s) {
  if (!s.user) return 'name';
  if (!s.filename) return 'file';
  return 'edit';
}
function render(s) {
  var step = stepOf(s);
  currentStep = step;
  codeDirty = false;

  if (step === 'name') {
    statusEl.innerHTML = '';
    app.innerHTML =
      '<div class="card">' +
        '<h3>Step 1 &mdash; Identify Yourself</h3>' +
        '<label>Your name</label>' +
        '<input id="nameInput" placeholder="Enter your name..." autocomplete="off" />' +
        '<div class="row"><button onclick="submitName()">Continue</button></div>' +
      '</div>';
    setTimeout(function(){ var el=document.getElementById('nameInput'); if(el) el.focus(); }, 50);
  } else if (step === 'file') {
    statusEl.innerHTML = 'User: <b>' + escapeHtml(s.user) + '</b>';
    app.innerHTML =
      '<div class="card">' +
        '<h3>Step 2 &mdash; Choose a File Name</h3>' +
        '<label>File name</label>' +
        '<input id="fileInput" placeholder="e.g. main.py" value="main.py" autocomplete="off" />' +
        '<div class="hint">Tip: use a .py extension</div>' +
        '<div class="row"><button onclick="submitFile()">Continue</button></div>' +
      '</div>';
    setTimeout(function(){ var el=document.getElementById('fileInput'); if(el) el.focus(); }, 50);
  } else {
    statusEl.innerHTML = 'User: <b>' + escapeHtml(s.user) + '</b> &nbsp;|&nbsp; File: <b>' +
      escapeHtml(s.filename) + '</b>';
    var fallback = '# Write your Python code here\nprint("Hello, Lyra Hub!")\n';
    var codeValue = s.code || fallback;
    app.innerHTML =
      '<div class="card">' +
        '<h3>Step 3 &mdash; Write Your Python Code</h3>' +
        '<textarea id="codeInput" placeholder="# Write Python here...">' +
          escapeHtml(codeValue) + '</textarea>' +
        '<div class="row">' +
          '<button id="runBtn" onclick="submitCode()">Run &amp; Save</button>' +
          '<button class="secondary" onclick="newSession()">New Session</button>' +
        '</div>' +
      '</div>' +
      '<div class="card">' +
        '<h3>Output</h3>' +
        '<div class="output-box" id="output">' +
          (s.output ? escapeHtml(s.output) : '&mdash; no output yet &mdash;') + '</div>' +
      '</div>' +
      '<div class="card">' +
        '<h3>Base64 Encoded Code</h3>' +
        '<div class="b64-box" id="b64">' +
          (s.base64 ? escapeHtml(s.base64) : '&mdash; nothing yet &mdash;') + '</div>' +
      '</div>';
    var ta = document.getElementById('codeInput');
    if (ta) {
      ta.addEventListener('input', function(){ codeDirty = true; });
      setTimeout(function(){ ta.focus(); }, 50);
    }
  }
}
async function submitName() {
  var v = document.getElementById('nameInput').value.trim();
  if (!v) { alert('Please enter your name'); return; }
  await post('/setname', { name: v });
  await sync(true);
}
async function submitFile() {
  var v = document.getElementById('fileInput').value.trim();
  if (!v) { alert('Please enter a file name'); return; }
  await post('/setfile', { filename: v });
  await sync(true);
}
async function submitCode() {
  var btn = document.getElementById('runBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
  var code = document.getElementById('codeInput').value;
  try {
    var res = await post('/run', { code: code });
    var out = document.getElementById('output');
    var b64 = document.getElementById('b64');
    if (out) out.textContent = res.output || '';
    if (b64) b64.textContent = res.base64 || '';
    codeDirty = false;
    lastVersion = res.version;
  } catch (e) {
    alert('Error: ' + e.message);
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Run & Save'; }
}
async function newSession() {
  if (!confirm('Start a new session? This clears the shared page for everyone.')) return;
  await post('/reset');
  await sync(true);
}
async function sync(force) {
  try {
    var s = await getState();
    var step = stepOf(s);
    if (force || step !== currentStep) {
      render(s);
      lastVersion = s.version;
    } else if (s.version !== lastVersion) {
      if (step === 'edit') {
        var out = document.getElementById('output');
        var b64 = document.getElementById('b64');
        if (out) out.textContent = s.output || '';
        if (b64) b64.textContent = s.base64 || '';
        if (!codeDirty) {
          var ta = document.getElementById('codeInput');
          if (ta) ta.value = s.code || '';
        }
      }
      lastVersion = s.version;
    }
  } catch (e) { console.error(e); }
}
async function pollLoop() {
  await sync(false);
  setTimeout(pollLoop, 2000);
}
(async function init() {
  await sync(true);
  pollLoop();
})();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/state")
def get_state():
    with _lock:
        return jsonify(STATE)


@app.route("/setname", methods=["POST"])
def setname():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    with _lock:
        STATE["user"] = name
        STATE["version"] += 1
    return jsonify({"ok": True})


@app.route("/setfile", methods=["POST"])
def setfile():
    data = request.get_json(silent=True) or {}
    fn = (data.get("filename") or "").strip()
    if not fn:
        return jsonify({"ok": False, "error": "Filename required"}), 400
    with _lock:
        STATE["filename"] = fn
        STATE["version"] += 1
    return jsonify({"ok": True})


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}
    code = data.get("code") or ""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py",
                                         delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        if not out.strip():
            out = "(No output)"
        out = out[:10000]
    except subprocess.TimeoutExpired:
        out = "Error: Execution timed out (5s limit)"
    except Exception as e:
        out = "Error: {}".format(e)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass

    b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
    with _lock:
        STATE["code"] = code
        STATE["output"] = out
        STATE["base64"] = b64
        STATE["version"] += 1
        version = STATE["version"]
    return jsonify({"ok": True, "output": out, "base64": b64, "version": version})


@app.route("/reset", methods=["POST"])
def reset():
    with _lock:
        STATE["user"] = None
        STATE["filename"] = None
        STATE["code"] = ""
        STATE["output"] = ""
        STATE["base64"] = ""
        STATE["version"] += 1
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
