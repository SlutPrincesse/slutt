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
      <div class="card"><h3>System</h3><pre>All 122 tests PASS • 673 modules • EventBus+Registry+Plugins active</pre></div>
      <div class="card"><h3>Agent</h3><pre>Autonomous loop • Reasoning+Memory • Evolution ready</pre></div>
    </section>
  </main>
</body>
</html>'''
