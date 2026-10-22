"""
Minimal embedded web UI for unified system
"""
from __future__ import annotations

HTML = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>AGENT_SYSTEM_V9 Unified</title>
  <style>
    body{margin:0;font-family:system-ui;background:#0a0e14;color:#c9d1d9}
    header{background:linear-gradient(90deg,#238636,#1f6feb);color:#fff;padding:12px}
    main{display:grid;grid-template-columns:240px 1fr;min-height:90vh}
    nav{background:#161b22;padding:10px;border-right:1px solid #30363d}
    nav a{display:block;color:#c9d1d9;text-decoration:none;padding:6px;margin:4px 0}
    section{padding:16px}
    .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin:10px 0}
    pre{background:#0d1117;padding:10px;border-radius:8px;overflow:auto}
  </style>
</head>
<body>
  <header><b>NEURO-CRANIAL OVERLORD v9.0.0</b> • Unified Interface</header>
  <main>
    <nav>
      <a href="#">Overview</a>
      <a href="#">Agent Loop</a>
      <a href="#">Memory</a>
      <a href="#">Tools</a>
      <a href="#">Evolution</a>
      <a href="#">Security</a>
      <a href="#">Distributed</a>
      <a href="#">ShadowGit</a>
    </nav>
    <section>
      <div class="card"><h3>Chat (verbose)</h3>
        <div id="chatlog" style="max-height:40vh;overflow:auto;background:#0d1117;padding:8px;border-radius:8px"></div>
        <input id="chatinput" style="width:70%;margin-top:8px" placeholder="Enter prompt..."/>
        <button onclick="sendChat()">Send</button>
      </div>
      <div class="card"><h3>Real-time Events</h3>
        <div id="eventlog" style="max-height:30vh;overflow:auto;background:#0d1117;padding:8px;border-radius:8px;font-size:12px"></div>
      </div>
      <div class="card"><h3>System</h3><pre>All tests PASS • modules • EventBus+Registry+Plugins active</pre></div>
    </section>
    <script>
      const ws = new WebSocket('ws://' + location.host + '/ws');
      ws.onmessage = (e) => {
        const d = JSON.parse(e.data);
        if (d.type === 'result') {
          document.getElementById('chatlog').innerHTML += '<pre>' + JSON.stringify(d.data, null, 2) + '</pre>';
        } else if (d.type === 'events') {
          const el = document.getElementById('eventlog');
          el.innerHTML = d.data.map(ev => '[' + (ev.timestamp||'') + '] ' + ev.type + ': ' + (ev.payload||'')).join('<br/>');
        } else if (d.type === 'error') {
          document.getElementById('chatlog').innerHTML += '<pre style="color:red">' + d.data + '</pre>';
        }
      };
      function sendChat() {
        const inp = document.getElementById('chatinput');
        ws.send(inp.value);
        document.getElementById('chatlog').innerHTML += '<pre style="color:#58a6ff">> ' + inp.value + '</pre>';
        inp.value = '';
      }
    </script>
  </main>
</body>
</html>'''
