"""Constants for the Nexus skills subsystem.

Port of skill-router's configuration constants:
- SKILL_ROOT_CANDIDATES, SKILL_SUBDIRS
- CATEGORY_KEYWORDS (10 categories)
- CN_EN_KEYWORD_MAP (Chinese -> English)
- SKILL_NAME_ALIASES (60+ skill aliases)
- DEFAULT_BLACKLIST
"""

from __future__ import annotations

import os

# ============================================================
# Skill root discovery
# ============================================================

SKILL_ROOT_CANDIDATES = [
    # DuMate default
    os.path.expanduser(
        "~/AppData/Roaming/qianfan-desktop-app/qianfan_desk_xdg/*/data/skills"
    ),
    # OpenCode style
    os.path.expanduser("~/.opencode/skills"),
    # Generic: alongside this script
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
    # Env var override
    os.environ.get("SKILL_ROOT", ""),
]

# Subdirectories within skill root to scan
SKILL_SUBDIRS = ["official", "user", "system", "community", ""]

# Blacklist: skills that should never be recommended (meta-skills, self, etc.)
DEFAULT_BLACKLIST = [
    "skill-router",
    "baidu-skill-guard",
]

# ============================================================
# Category keyword map - used for category boost scoring
# ============================================================

CATEGORY_KEYWORDS = {
    "writing": [
        "write", "draft", "article", "blog", "novel", "story", "fiction",
        "content", "copy", "copywriting", "essay", "report",
        "xie", "xiezuo", "wenzhang", "xiaoshuo", "gushi", "baogao",
        "xiezuoshier", "neirong",
    ],
    "code": [
        "code", "coding", "program", "debug", "refactor", "review",
        "python", "rust", "javascript", "typescript", "go", "java",
        "api", "function", "class", "bug", "test", "unit test",
        "daima", "biancheng", "diaoshi", "chonggou", "jiema",
    ],
    "data": [
        "data", "analysis", "excel", "csv", "xlsx", "spreadsheet",
        "chart", "graph", "visualize", "statistics", "pivot",
        "shuju", "fenxi", "tubiao", "biaoge",
    ],
    "research": [
        "research", "search", "find", "investigate", "survey", "study",
        "analyze", "deep dive", "literature",
        "yanjiu", "diaocha", "sousuo", "fenxi",
    ],
    "document": [
        "pdf", "word", "docx", "pptx", "excel", "xlsx",
        "document", "slide", "presentation", "spreadsheet",
        "wendang", "ppt", "biaoge",
    ],
    "media": [
        "image", "video", "audio", "music", "gif", "photo",
        "generate", "create", "edit", "convert",
        "tupian", "shipin", "yinyue", "shengcheng",
    ],
    "communication": [
        "email", "message", "send", "notify", "chat", "calendar",
        "meeting", "schedule",
        "youjian", "fasong", "rili", "huiyi",
    ],
    "business": [
        "market", "strategy", "competitor", "analysis", "positioning",
        "launch", "go-to-market", "GTM", "marketing", "sales", "customer",
        "shichang", "celue", "yingxiao", "xiaoshou",
    ],
    "system": [
        "file", "directory", "shell", "command", "process", "terminal",
        "bash", "script", "automation",
        "wenjian", "mingling", "zidonghua",
    ],
    "ai": [
        "ai", "model", "llm", "prompt", "agent", "mcp",
        "intelligence", "machine learning",
        "moxing", "zhineng",
    ],
}

# ============================================================
# Cross-language keyword map: Chinese -> English equivalents
# ============================================================

CN_EN_KEYWORD_MAP = {
    "数据": ["data"],
    "分析": ["analysis", "analyze"],
    "统计": ["statistics", "statistical"],
    "可视化": ["visualize", "visualization", "chart", "graph"],
    "图表": ["chart", "graph", "plot"],
    "表格": ["table", "spreadsheet", "excel"],
    "文档": ["document", "doc"],
    "报告": ["report"],
    "生成": ["generate", "create"],
    "转换": ["convert", "transform"],
    "解析": ["parse", "extract"],
    "识别": ["recognize", "recognition", "identify"],
    "翻译": ["translate", "translation"],
    "搜索": ["search"],
    "上传": ["upload"],
    "下载": ["download"],
    "邮件": ["email", "mail"],
    "发送": ["send"],
    "图片": ["image", "picture", "photo"],
    "视频": ["video"],
    "音频": ["audio"],
    "语音": ["voice", "speech"],
    "文字": ["text"],
    "网页": ["web", "webpage", "browser"],
    "网站": ["website", "site"],
    "代码": ["code"],
    "脚本": ["script"],
    "配置": ["config", "configuration"],
    "部署": ["deploy", "deployment"],
    "测试": ["test", "testing"],
    "调试": ["debug", "debugging"],
    "爬虫": ["crawler", "scrape"],
    "机器学习": ["machine learning", "ml"],
    "深度学习": ["deep learning"],
    "模型": ["model"],
    "合同": ["contract"],
    "发票": ["invoice"],
    "客户": ["customer", "client"],
    "项目": ["project"],
    "流程": ["workflow", "process"],
    "审批": ["approval", "approve"],
    "风险": ["risk"],
    "密码": ["password", "credential"],
    "安全": ["security", "secure"],
    "网络": ["network"],
    "数据库": ["database", "db"],
    "服务器": ["server"],
    "文件": ["file"],
    "目录": ["directory", "folder"],
    "压缩": ["compress", "zip"],
    "合并": ["merge", "combine"],
    "拆分": ["split", "separate"],
    "排序": ["sort"],
    "过滤": ["filter"],
    "聚合": ["aggregate", "aggregation"],
    "导出": ["export"],
    "导入": ["import"],
}

# ============================================================
# Skill name aliases - when these keywords appear in a task,
# the corresponding skill gets a big score boost
# ============================================================

SKILL_NAME_ALIASES = {
    "pdf": ["pdf", "PDF"],
    "xlsx": ["xlsx", "xls", "excel", "Excel", "csv", "spreadsheet", "电子表格", "表格"],
    "docx": ["docx", "doc", "word", "Word", "文档"],
    "pptx": ["pptx", "ppt", "PPT", "slide", "presentation", "演示文稿", "幻灯片"],
    "python": ["python", "Python", "py", "pip"],
    "data-analysis": [
        "数据分析", "data analysis", "统计分析", "分析数据", "统计数据",
        "数据处理", "分析这份", "分析这些", "分析这个", "做统计",
    ],
    "markdown-converter": ["转Markdown", "文档转换", "markitdown"],
    "visualized-output": ["可视化", "图表渲染", "流程图", "架构图", "思维导图"],
    "python-dataviz": ["Python图表", "matplotlib", "seaborn", "数据可视化"],
    "baidu-image-gen": ["生图", "文生图", "图生图", "图片生成", "AI绘图", "画图"],
    "baidu-novel-gen": ["写小说", "小说", "网络小说", "创作小说", "novel"],
    "novel-writing-suite": ["小说", "novel", "写作套件"],
    "humanizer": ["去AI味", "AI味", "humanize", "去AI"],
    "baidu-text-to-speech": ["TTS", "语音合成", "文字转语音", "朗读"],
    "baidu-speech-recognition": ["ASR", "语音识别", "语音转文字"],
    "baidu-voice-cloning": ["声音复刻", "声音克隆", "voice clone"],
    "baidu-digital-human": ["数字人", "虚拟主播", "digital human", "数字分身"],
    "baidu-ocr-general": ["OCR", "文字识别", "图片转文字"],
    "baidu-ocr-education": ["试卷识别", "题目识别", "试卷OCR"],
    "baidu-object-extraction": [
        "抠图", "背景去除", "去背景", "去掉背景", "去除背景",
        "背景去掉", "背景擦除", "擦除背景", "提取主体", "去图背景",
    ],
    "baidu-video-gen": ["生成视频", "视频生成", "短剧视频"],
    "dumate-browser-use": [
        "浏览器", "网页操作", "browser", "自动化网页",
        "打开网页", "填表", "网页填表",
    ],
    "doubao-vision": ["图片识别", "图片分析", "视觉识别"],
    "outlook": ["发邮件", "收邮件", "Outlook", "邮件管理", "发一封邮件"],
    "tencent-docs": ["腾讯文档", "在线文档", "docs.qq.com"],
    "tencent-meeting-mcp": ["腾讯会议", "预约会议", "会议管理"],
    "weread-skills": ["微信读书", "读书笔记", "书架管理"],
    "infoflow-calendar": ["如流日程", "创建日程", "预约会议", "如流会议"],
    "infoflow-im-message": ["如流消息", "如流机器人", "发群消息"],
    "so-send-message": ["如流发消息", "发送通知", "群组消息"],
    "meituan-paotui": ["美团跑腿", "跑腿下单", "同城配送"],
    "didi-ride-skill": [
        "打车", "叫车", "网约车", "滴滴", "叫个车",
        "打车去", "去机场", "回家", "上班", "下班",
    ],
    "git-commit": ["git commit", "提交代码", "commit"],
    "code-review": ["代码审查", "code review", "review代码"],
    "content-writer": ["写文案", "小红书", "公众号", "抖音文案", "知乎"],
    "copywriting": ["广告文案", "landing page", "销售文案", "营销文案"],
    "mcp-builder": ["MCP服务器", "创建MCP", "Model Context Protocol"],
    "skill-creator": ["创建技能", "创建skill", "技能创建"],
    "brainstorming": ["头脑风暴", "需求探索", "功能设计"],
    "frontend-design": ["前端设计", "UI组件", "网页设计"],
    "ui-ux-pro-max": ["UI设计", "UX设计", "界面设计", "交互设计"],
    "theme-factory": ["主题样式", "配色方案", "theme"],
    "ezgif": ["GIF制作", "GIF转换", "动图编辑"],
    "algorithmic-art": ["算法艺术", "p5.js", "生成艺术"],
    "remotion-best-practices": ["Remotion", "React视频"],
    "writing-plans": ["写计划", "实现计划", "技术方案"],
    "executing-plans": ["执行计划", "实施计划"],
    "test-driven-development": ["TDD", "测试驱动开发"],
    "security-best-practices": ["安全审查", "安全最佳实践"],
    "marketing-strategy-pmm": ["产品营销", "GTM", "市场策略"],
    "product-analytics": ["产品分析", "KPI", "指标看板"],
    "consulting-analysis": ["咨询报告", "市场分析", "行业研究"],
    "summarize-pro": ["总结", "摘要", "summarize", "TL;DR"],
    "free-models": ["免费模型", "GLM", "DeepSeek", "智谱"],
    "gpt55": ["GPT-5.5", "军师模式", "出谋划策", "拍板评估"],
}
