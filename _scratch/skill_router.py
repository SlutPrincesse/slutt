#!/usr/bin/env python3
"""
Skill Router - Universal skill discovery and routing engine.
Scans all installed skills, matches them against a task description,
and returns ranked recommendations with match reasoning.

Zero external dependencies. Pure Python 3.8+. Portable to any agent.
"""

import os
import re
import json
import sys
import time
import argparse
import hashlib
import pickle
from pathlib import Path
from datetime import datetime

# ============================================================
# Config
# ============================================================

# Try multiple candidate skill root directories
# Supports: DuMate, OpenCode, custom agent layouts
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

# Cache file location
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "skill_index.pkl")

# Blacklist: skills that should never be recommended (meta-skills, self, etc.)
DEFAULT_BLACKLIST = [
    "skill-router",  # Don't recommend self
    "baidu-skill-guard",  # Security guard, not a task skill
]

# Category keyword map - used for category boost scoring
CATEGORY_KEYWORDS = {
    "writing": [
        "write",
        "draft",
        "article",
        "blog",
        "novel",
        "story",
        "fiction",
        "content",
        "copy",
        "copywriting",
        "essay",
        "report",
        "xie",
        "xiezuo",
        "wenzhang",
        "xiaoshuo",
        "gushi",
        "baogao",
        "xiezuoshier",
        "neirong",
        "xiezuo",
    ],
    "code": [
        "code",
        "coding",
        "program",
        "debug",
        "refactor",
        "review",
        "python",
        "rust",
        "javascript",
        "typescript",
        "go",
        "java",
        "api",
        "function",
        "class",
        "bug",
        "test",
        "unit test",
        "daima",
        "biancheng",
        "diaoshi",
        "chonggou",
        "jiema",
    ],
    "data": [
        "data",
        "analysis",
        "excel",
        "csv",
        "xlsx",
        "spreadsheet",
        "chart",
        "graph",
        "visualize",
        "statistics",
        "pivot",
        "shuju",
        "fenxi",
        "tubiao",
        "biaoge",
    ],
    "research": [
        "research",
        "search",
        "find",
        "investigate",
        "survey",
        "study",
        "analyze",
        "deep dive",
        "literature",
        "yanjiu",
        "diaocha",
        "sousuo",
        "fenxi",
    ],
    "document": [
        "pdf",
        "word",
        "docx",
        "pptx",
        "excel",
        "xlsx",
        "document",
        "slide",
        "presentation",
        "spreadsheet",
        "wendang",
        "ppt",
        "biaoge",
    ],
    "media": [
        "image",
        "video",
        "audio",
        "music",
        "gif",
        "photo",
        "generate",
        "create",
        "edit",
        "convert",
        "tupian",
        "shipin",
        "yinyue",
        "shengcheng",
    ],
    "communication": [
        "email",
        "message",
        "send",
        "notify",
        "chat",
        "calendar",
        "meeting",
        "schedule",
        "youjian",
        "fasong",
        "rili",
        "huiyi",
    ],
    "business": [
        "market",
        "strategy",
        "competitor",
        "analysis",
        "positioning",
        "launch",
        "go-to-market",
        "GTM",
        "marketing",
        "sales",
        "customer",
        "shichang",
        "celue",
        "yingxiao",
        "xiaoshou",
    ],
    "system": [
        "file",
        "directory",
        "shell",
        "command",
        "process",
        "terminal",
        "bash",
        "script",
        "automation",
        "wenjian",
        "mingling",
        "zidonghua",
    ],
    "ai": [
        "ai",
        "model",
        "llm",
        "prompt",
        "agent",
        "mcp",
        "intelligence",
        "machine learning",
        "moxing",
        "zhineng",
    ],
}

# Cross-language keyword map: Chinese keyword -> English equivalents
# Used to bridge the gap when skill descriptions are English but tasks are Chinese
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


# When these keywords appear in the task, the corresponding skill gets a big score boost
SKILL_NAME_ALIASES = {
    "pdf": ["pdf", "PDF"],
    "xlsx": ["xlsx", "xls", "excel", "Excel", "csv", "spreadsheet", "电子表格", "表格"],
    "docx": ["docx", "doc", "word", "Word", "文档"],
    "pptx": ["pptx", "ppt", "PPT", "slide", "presentation", "演示文稿", "幻灯片"],
    "python": ["python", "Python", "py", "pip"],
    "data-analysis": [
        "数据分析",
        "data analysis",
        "统计分析",
        "分析数据",
        "统计数据",
        "数据处理",
        "分析这份",
        "分析这些",
        "分析这个",
        "做统计",
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
        "抠图",
        "背景去除",
        "去背景",
        "去掉背景",
        "去除背景",
        "背景去掉",
        "背景擦除",
        "擦除背景",
        "提取主体",
        "去图背景",
    ],
    "baidu-video-gen": [
        "生成视频",
        "视频生成",
        "文生视频",
        "图生视频",
        "短视频生成",
        "做视频",
    ],
    "baidu-text-video": ["remotion", "程序化视频", "React视频", "代码生成视频"],
    "baidu-drive": ["百度网盘", "网盘", "云盘", "baidu drive"],
    "baidu-trending": ["热搜", "热门话题", "trending", "榜单", "热点"],
    "baidu-script-gen": ["短剧剧本", "剧本生成", "写剧本"],
    "baidu-drama-gen": ["短剧视频", "短剧生成"],
    "baidu-ai-map": ["百度地图", "地图API", "路线规划", "POI搜索"],
    "baidu-baike-data": ["百度百科", "百科查询", "词条"],
    "dumate-browser-use": [
        "浏览器",
        "网页操作",
        "browser",
        "自动化网页",
        "打开网页",
        "填表",
        "网页填表",
    ],
    "doubao-vision": ["图片识别", "图片分析", "视觉识别"],
    "outlook": ["发邮件", "收邮件", "Outlook", "邮件管理", "发一封邮件"],
    "baidu-exchange-skill": ["百度邮箱", "企业邮箱", "百度企业邮箱"],
    "tencent-docs": ["腾讯文档", "在线文档", "docs.qq.com"],
    "tencent-meeting-mcp": ["腾讯会议", "预约会议", "会议管理"],
    "weread-skills": ["微信读书", "读书笔记", "书架管理"],
    "infoflow-calendar": ["如流日程", "创建日程", "预约会议", "如流会议"],
    "infoflow-im-message": ["如流消息", "如流机器人", "发群消息"],
    "so-send-message": ["如流发消息", "发送通知", "群组消息"],
    "meituan-paotui": ["美团跑腿", "跑腿下单", "同城配送"],
    "didi-ride-skill": [
        "打车",
        "叫车",
        "网约车",
        "滴滴",
        "叫个车",
        "打车去",
        "去机场",
        "回家",
        "上班",
        "下班",
    ],
    "git-commit": ["git commit", "提交代码", "commit"],
    "code-review": ["代码审查", "code review", "review代码"],
    "content-writer": ["写文案", "小红书", "公众号", "抖音文案", "知乎"],
    "copywriting": ["广告文案", "landing page", "销售文案", "营销文案"],
    "icafe-card-assistant": ["icafe", "卡片查询", "研发卡片"],
    "ku-doc-manage": ["知识库文档", "ku文档", "百度知识库"],
    "knowledge-fetch": ["拉取知识", "下载知识", "知识获取"],
    "notion": ["Notion", "notion页面", "notion数据库"],
    "shengsuan-skill": ["胜算", "DataBuilder", "逻辑建模"],
    "famou-artifact-generator": ["Famou", "优化任务", "进化算法"],
    "tieba-claw": ["百度贴吧", "发帖", "贴吧"],
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
    "agnes": ["Agnes", "免费API", "文本推理"],
    "free-models": ["免费模型", "GLM", "DeepSeek", "智谱"],
    "gpt55": ["GPT-5.5", "军师模式", "出谋划策", "拍板评估"],
}

# ============================================================
# Skill Index: Scan & Parse
# ============================================================


class SkillIndex:
    """Scans skill directories, parses SKILL.md files, builds searchable index."""

    def __init__(self, skill_roots=None, blacklist=None):
        self.skill_roots = skill_roots or self._find_skill_roots()
        self.blacklist = set(blacklist or DEFAULT_BLACKLIST)
        self.skills = {}  # name -> SkillInfo dict
        self._cache_valid = False

    def _find_skill_roots(self):
        """Auto-discover skill root directories."""
        import glob

        roots = set()
        for pattern in SKILL_ROOT_CANDIDATES:
            if not pattern:
                continue
            # Expand wildcards
            for matched in glob.glob(pattern):
                if os.path.isdir(matched):
                    roots.add(os.path.abspath(matched))
        return list(roots)

    def _find_skill_dirs(self):
        """Find all skill directories under configured roots."""
        skill_dirs = []
        for root in self.skill_roots:
            for subdir in SKILL_SUBDIRS:
                base = os.path.join(root, subdir) if subdir else root
                if not os.path.isdir(base):
                    continue
                for entry in os.listdir(base):
                    skill_path = os.path.join(base, entry)
                    skill_md = os.path.join(skill_path, "SKILL.md")
                    if os.path.isfile(skill_md):
                        skill_dirs.append(
                            {
                                "name": entry,
                                "path": skill_path,
                                "skill_md": skill_md,
                                "tier": subdir or "root",
                            }
                        )
        return skill_dirs

    def _parse_skill_md(self, skill_md_path):
        """Parse a SKILL.md file, extract metadata and trigger keywords."""
        try:
            with open(skill_md_path, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
        except Exception:
            return None

        info = {
            "name": "",
            "description": "",
            "triggers": [],
            "keywords": [],
            "no_triggers": [],  # "DO NOT TRIGGER" patterns
            "tools": [],  # Tool names mentioned
            "raw_text": content[:8000],  # Keep first 8000 chars for matching
            "full_length": len(content),
        }

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            name_match = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
            if name_match:
                info["name"] = name_match.group(1).strip().strip("\"'")

            # Parse description - handle multiline YAML scalars (>, |)
            desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
            if desc_match:
                first_line = desc_match.group(1).strip().strip("\"'")
                if first_line in (">", "|", ">-", "|-", ">", "|"):
                    # Folded/literal scalar: description is on following indented lines
                    fm_lines = fm.split("\n")
                    desc_lines = []
                    in_desc = False
                    for line in fm_lines:
                        if in_desc:
                            if line.startswith("  ") or line.startswith("\t"):
                                desc_lines.append(line.strip())
                            elif line.strip() == "":
                                continue
                            else:
                                break
                        elif line.strip().startswith("description:"):
                            in_desc = True
                    info["description"] = " ".join(desc_lines)
                else:
                    info["description"] = first_line
            else:
                # Try inline description without value on same line
                pass

        # Fallback: if no frontmatter, try H1 header
        if not info["name"]:
            h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if h1_match:
                name = h1_match.group(1).strip()
                name = re.sub(r"^Skill:\s*", "", name, flags=re.IGNORECASE)
                info["name"] = name

        # Extract description from first paragraph if not in frontmatter
        if not info["description"]:
            lines = content.split("\n")
            for line in lines[1:20]:
                line = line.strip()
                if (
                    line
                    and not line.startswith("#")
                    and not line.startswith("---")
                    and len(line) > 15
                ):
                    info["description"] = line[:300]
                    break

        # Extract trigger keywords from dedicated trigger sections only
        # Only extract short keyword phrases (2-30 chars), not full sentences
        trigger_patterns = [
            # "触发词：" / "触发关键词：" / "关键词：" / "Triggers:"
            # Capture only until end of line (not across sections)
            r"(?:触发词|触发关键词|关键词)\s*[:：]\s*(.+)",
            r"(?:Triggers?|TRIGGER)\s*[:：]\s*(.+)",
        ]
        for pattern in trigger_patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            for m in matches:
                # Split by comma, semicolon, pipe, or Chinese comma
                items = re.split(r"[,;|，；、]+", m)
                for item in items:
                    item = item.strip().strip('"\'""[]()（）「」『』')
                    # Only accept short keyword phrases, not full sentences
                    if item and 2 <= len(item) <= 30:
                        info["triggers"].append(item)

        # Also extract from "触发场景" / "适用场景" sections, but only take
        # short bullet items (lines starting with - or *)
        scene_pattern = r"(?:触发场景|适用场景|何时使用|When to use|Use when)\s*[:：]?\s*\n((?:.*\n)*?)(?=\n#|\n##|\Z)"
        scene_match = re.search(scene_pattern, content, re.IGNORECASE)
        if scene_match:
            scene_text = scene_match.group(1)
            # Extract bullet items
            bullets = re.findall(r"^[\-\*]\s*(.+)", scene_text, re.MULTILINE)
            for b in bullets:
                b = b.strip().strip('"\'""[]()（）「」『』')
                # Take first phrase before Chinese comma/period if too long
                if len(b) > 30:
                    parts = re.split(r"[，。；,;.]", b)
                    b = parts[0].strip()
                if b and 2 <= len(b) <= 30:
                    info["triggers"].append(b)

        # Deduplicate triggers
        info["triggers"] = list(dict.fromkeys(info["triggers"]))

        # Extract "DO NOT TRIGGER" / "不触发" / "不适用" patterns
        no_trigger_patterns = [
            r"(?:DO NOT TRIGGER|不触发|不适用|不要使用)\s*[:：]?\s*(.*?)(?=\n#|\n##|\Z)",
        ]
        for pattern in no_trigger_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for m in matches:
                items = re.split(r"[,;|;，；\n]+", m)
                for item in items:
                    item = item.strip().strip('"\'""')
                    if item and len(item) > 1:
                        info["no_triggers"].append(item)

        # Extract tool/method names from bash/code blocks
        tool_pattern = re.findall(
            r'(?:python|bash|node)\s+["\']?[^/]+/(\w+)\.py["\']?\s+(\w+)', content
        )
        for script_name, method_name in tool_pattern:
            info["tools"].append(method_name)

        # Also look for "调用方式" sections
        call_sections = re.findall(
            r"调用方式\s*[:：]\s*(.*?)(?=\n###|\n##|\n#|\Z)", content, re.DOTALL
        )
        for section in call_sections:
            tool_match = re.search(r'(\w+)\.py["\']?\s+(\w+)', section)
            if tool_match:
                info["tools"].append(tool_match.group(2))

        # Deduplicate
        info["tools"] = list(dict.fromkeys(info["tools"]))

        # Build keyword bag from all text
        keyword_text = (
            info["description"] + " " + " ".join(info["triggers"]) + " " + info["name"]
        )
        info["keywords"] = self._extract_keywords(keyword_text)

        return info

    def _extract_keywords(self, text):
        """Extract meaningful keywords from text (both Chinese and English)."""
        keywords = set()

        # English words: 2+ chars. Use lookaround for Chinese-English boundaries
        # since \b doesn't work at CJK-ASCII boundaries
        en_words = re.findall(
            r"(?:^|[\s\u4e00-\u9fff,;:!?()\"'\[\]{}|/\\])([a-zA-Z]{2,}[0-9a-zA-Z]*)",
            text,
        )
        en_words += re.findall(r"\b([a-zA-Z]{2,}[0-9a-zA-Z]*)\b", text)
        for w in en_words:
            w_lower = w.lower()
            if w_lower not in STOP_WORDS_EN and len(w_lower) >= 2:
                keywords.add(w_lower)

        # Chinese: 2-grams + 3-grams, filtered by stop words
        cn_segments = re.findall(r"[\u4e00-\u9fff]+", text)
        for seg in cn_segments:
            if len(seg) >= 2:
                # Add full segment if short and not a stop word
                if len(seg) <= 6 and seg not in STOP_WORDS_CN:
                    keywords.add(seg)
                # 2-grams
                for i in range(len(seg) - 1):
                    gram = seg[i : i + 2]
                    if gram not in STOP_WORDS_CN:
                        keywords.add(gram)
                # 3-grams
                if len(seg) >= 3:
                    for i in range(len(seg) - 2):
                        gram = seg[i : i + 3]
                        if gram not in STOP_WORDS_CN:
                            keywords.add(gram)

        # Cross-language expansion: add English equivalents for Chinese keywords
        extra = set()
        for kw in keywords:
            if kw in CN_EN_KEYWORD_MAP:
                for en_word in CN_EN_KEYWORD_MAP[kw]:
                    extra.add(en_word.lower())
        keywords |= extra

        return list(keywords)

    def build_index(self, use_cache=True, force_refresh=False):
        """Scan all skill directories and build the search index."""
        # Check cache
        if use_cache and not force_refresh and self._load_cache():
            return len(self.skills)

        self.skills.clear()
        skill_dirs = self._find_skill_dirs()

        for sd in skill_dirs:
            name = sd["name"]
            if name in self.blacklist:
                continue
            info = self._parse_skill_md(sd["skill_md"])
            if info and info["name"]:
                info["path"] = sd["path"]
                info["tier"] = sd["tier"]
                # Use directory name as canonical name if frontmatter name differs
                info["dir_name"] = name
                # Pre-compute description keywords for overlap scoring
                info["keywords"] = self._extract_keywords(info.get("description", ""))
                self.skills[name] = info

        # Save cache
        self._save_cache()
        self._cache_valid = True
        return len(self.skills)

    # --------------------------------------------------------
    # Cache management
    # --------------------------------------------------------

    def _cache_signature(self):
        """Generate a signature based on SKILL.md file modification times."""
        sig_parts = []
        for root in self.skill_roots:
            for subdir in SKILL_SUBDIRS:
                base = os.path.join(root, subdir) if subdir else root
                if not os.path.isdir(base):
                    continue
                for entry in sorted(os.listdir(base)):
                    md = os.path.join(base, entry, "SKILL.md")
                    if os.path.isfile(md):
                        mtime = os.path.getmtime(md)
                        sig_parts.append(f"{entry}:{mtime}")
        return hashlib.md5("|".join(sig_parts).encode()).hexdigest()

    def _save_cache(self):
        """Save index to cache file."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            sig = self._cache_signature()
            data = {
                "signature": sig,
                "skills": self.skills,
                "built_at": datetime.now().isoformat(),
            }
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass  # Cache is optional

    def _load_cache(self):
        """Load index from cache if still valid."""
        try:
            if not os.path.isfile(CACHE_FILE):
                return False
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            # Check signature
            current_sig = self._cache_signature()
            if data.get("signature") != current_sig:
                return False
            self.skills = data.get("skills", {})
            self._cache_valid = True
            return True
        except Exception:
            return False


# ============================================================
# Matcher: Score & Rank Skills
# ============================================================


class SkillMatcher:
    """Matches a task description against the skill index using multi-layer scoring."""

    def __init__(self, index):
        self.index = index

    def match(self, task_description, top_k=10, min_score=15, verbose=False):
        """
        Match task description against all skills.
        Returns sorted list of match results.
        """
        results = []
        task_lower = task_description.lower()

        # Extract task keywords
        task_keywords = self._extract_task_keywords(task_description)

        # Detect task category for category boost
        task_categories = self._detect_category(task_description)

        if verbose:
            import sys as _sys

            print(f"[debug] Task keywords: {task_keywords}", file=_sys.stderr)
            print(f"[debug] Task categories: {task_categories}", file=_sys.stderr)

        for skill_name, skill_info in self.index.skills.items():
            score = 0
            match_reasons = []

            # --- Layer 0: Skill name direct match (highest priority) ---
            # If the skill name appears in the task description, it's almost certainly relevant
            dir_name = skill_info.get("dir_name", skill_name).lower()
            display_name = skill_info.get("name", skill_name).lower()
            for sname in [dir_name, display_name]:
                if len(sname) >= 3 and sname in task_lower:
                    score += 50.0
                    match_reasons.append(f"name_match: '{sname}'")
                    break

            # --- Layer 0b: Alias match (file formats, common task types) ---
            aliases = SKILL_NAME_ALIASES.get(skill_info.get("dir_name", skill_name), [])
            for alias in aliases:
                if alias in task_description:
                    score += 45.0
                    match_reasons.append(f"alias_match: '{alias}'")
                    break

            # --- Layer 1: Trigger keyword match (high weight) ---
            trigger_score, trigger_hits = self._score_triggers(
                task_keywords, skill_info
            )
            if trigger_score > 0:
                score += trigger_score * 2.0  # Weight: 2x (lowered from 3x)
                for hit in trigger_hits:
                    match_reasons.append(f"trigger: '{hit}'")

            # --- Layer 2: Description keyword overlap (medium weight) ---
            desc_score, desc_hits = self._score_description_overlap(
                task_keywords, skill_info
            )
            if desc_score > 0:
                score += desc_score * 2.0  # Weight: 2x
                for hit in desc_hits:
                    match_reasons.append(f"keyword: '{hit}'")

            # --- Layer 3: Fuzzy text search in raw SKILL.md (low weight, safety net) ---
            fuzzy_score, fuzzy_hits = self._score_fuzzy_text(task_keywords, skill_info)
            if fuzzy_score > 0:
                score += fuzzy_score * 1.0  # Weight: 1x
                for hit in fuzzy_hits[:3]:
                    match_reasons.append(f"fuzzy: '{hit}'")

            # --- Layer 4: Category boost ---
            if task_categories:
                cat_score = self._score_category_boost(task_categories, skill_info)
                if cat_score > 0:
                    score += cat_score * 1.5
                    match_reasons.append(f"category: {', '.join(task_categories)}")

            # --- Layer 5: Negative filter (DO NOT TRIGGER) ---
            negative_hits = self._check_negative_filters(task_keywords, skill_info)
            if negative_hits:
                score -= 20  # Heavy penalty
                for hit in negative_hits:
                    match_reasons.append(f"NEGATIVE: '{hit}'")

            # Only include skills with score above threshold
            if score >= min_score:
                results.append(
                    {
                        "skill_name": skill_info.get("dir_name", skill_name),
                        "display_name": skill_info.get("name", skill_name),
                        "description": skill_info.get("description", "")[:200],
                        "score": round(score, 2),
                        "tier": skill_info.get("tier", "unknown"),
                        "path": skill_info.get("path", ""),
                        "tools": skill_info.get("tools", []),
                        "reasons": match_reasons,
                        "recommendation": self._make_recommendation(score),
                    }
                )

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        # Return top_k
        return results[:top_k]

    def _extract_task_keywords(self, task_description):
        """Extract keywords from the user's task description."""
        keywords = set()
        text = task_description.lower()

        # English words (2+ chars) - handle CJK-ASCII boundary
        en_words = re.findall(
            r"(?:^|[\s\u4e00-\u9fff,;:!?()\"'\[\]{}|/\\])([a-zA-Z]{2,}[0-9a-zA-Z]*)",
            task_description,
        )
        en_words += re.findall(r"\b([a-zA-Z]{2,}[0-9a-zA-Z]*)\b", text)
        for w in en_words:
            w_lower = w.lower()
            if w_lower not in STOP_WORDS_EN:
                keywords.add(w_lower)

        # Chinese: 2-grams + 3-grams, filtered by stop words
        cn_segments = re.findall(r"[\u4e00-\u9fff]+", task_description)
        for seg in cn_segments:
            if len(seg) >= 2:
                # Add full segment if short and not stop word
                if len(seg) <= 6 and seg not in STOP_WORDS_CN:
                    keywords.add(seg)
                # 2-grams
                for i in range(len(seg) - 1):
                    gram = seg[i : i + 2]
                    if gram not in STOP_WORDS_CN:
                        keywords.add(gram)
                # 3-grams
                if len(seg) >= 3:
                    for i in range(len(seg) - 2):
                        gram = seg[i : i + 3]
                        if gram not in STOP_WORDS_CN:
                            keywords.add(gram)

        # Cross-language expansion: add English equivalents for Chinese keywords
        extra = set()
        for kw in keywords:
            if kw in CN_EN_KEYWORD_MAP:
                for en_word in CN_EN_KEYWORD_MAP[kw]:
                    extra.add(en_word.lower())
        keywords |= extra

        return keywords

    def _detect_category(self, task_description):
        """Detect task category from description for boost scoring."""
        text = task_description.lower()
        categories = []
        for cat, kws in CATEGORY_KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    categories.append(cat)
                    break
        return categories

    def _score_triggers(self, task_keywords, skill_info):
        """Score trigger keyword matches. Each task keyword only scores once per skill."""
        score = 0.0
        hits = []
        triggers = skill_info.get("triggers", [])

        # Build a set of which task keywords matched, to avoid double-counting
        matched_task_kws = set()

        for trigger in triggers:
            trigger_lower = trigger.lower().strip()
            if not trigger_lower or len(trigger_lower) < 2:
                continue
            if len(trigger_lower) > 30:
                continue
            if trigger_lower in STOP_WORDS_CN or trigger_lower in STOP_WORDS_EN:
                continue

            best_score_for_trigger = 0.0
            best_kw = None

            for kw in task_keywords:
                if kw in matched_task_kws:
                    continue  # This task keyword already matched another trigger
                if kw in STOP_WORDS_CN:
                    continue

                if trigger_lower == kw:
                    s = 10.0 + (len(kw) / 5.0)
                    if s > best_score_for_trigger:
                        best_score_for_trigger = s
                        best_kw = kw
                elif len(trigger_lower) <= 15 and kw in trigger_lower and len(kw) >= 2:
                    s = 8.0 + (len(kw) / 10.0)
                    if s > best_score_for_trigger:
                        best_score_for_trigger = s
                        best_kw = kw
                elif trigger_lower in kw and len(trigger_lower) >= 2:
                    s = 8.0 + (len(trigger_lower) / 10.0)
                    if s > best_score_for_trigger:
                        best_score_for_trigger = s
                        best_kw = kw

            if best_score_for_trigger > 0 and best_kw:
                score += best_score_for_trigger
                hits.append(trigger)
                matched_task_kws.add(best_kw)

        return score, list(dict.fromkeys(hits))

    def _score_description_overlap(self, task_keywords, skill_info):
        """Score keyword overlap between task and skill description."""
        desc_keywords = set(skill_info.get("keywords", []))
        if not desc_keywords:
            return 0.0, []

        overlap = task_keywords & desc_keywords
        if not overlap:
            return 0.0, []

        # Use absolute overlap count × per-match weight
        # (Jaccard doesn't work well with 2-gram expansion which inflates the union)
        score = len(overlap) * 5.0

        return score, list(overlap)

    def _score_fuzzy_text(self, task_keywords, skill_info):
        """Fuzzy match task keywords against raw SKILL.md text."""
        raw = skill_info.get("raw_text", "").lower()
        if not raw:
            return 0.0, []

        score = 0.0
        hits = []
        for kw in task_keywords:
            if len(kw) < 2:
                continue
            count = raw.count(kw)
            if count > 0:
                s = min(count * 1.5, 6.0)
                score += s
                hits.append(kw)
        return score, list(dict.fromkeys(hits))

    def _score_category_boost(self, task_categories, skill_info):
        """Boost score for skills whose description matches detected category."""
        desc = skill_info.get("description", "").lower()
        triggers = " ".join(skill_info.get("triggers", [])).lower()
        combined = desc + " " + triggers
        if not combined:
            return 0.0

        boost = 0.0
        for cat in task_categories:
            cat_kws = CATEGORY_KEYWORDS.get(cat, [])
            for kw in cat_kws:
                if kw in combined:
                    boost += 2.0
                    break
        return boost

    def _check_negative_filters(self, task_keywords, skill_info):
        """Check if task matches any DO NOT TRIGGER patterns."""
        hits = []
        for no_trigger in skill_info.get("no_triggers", []):
            nt_lower = no_trigger.lower().strip()
            if not nt_lower:
                continue
            for kw in task_keywords:
                if nt_lower in kw or kw in nt_lower:
                    hits.append(no_trigger)
                    break
        return hits

    def _make_recommendation(self, score):
        """Generate recommendation label based on score."""
        if score >= 50:
            return "STRONG_MATCH"
        elif score >= 30:
            return "GOOD_MATCH"
        elif score >= 20:
            return "POSSIBLE_MATCH"
        else:
            return "WEAK_MATCH"


# ============================================================
# Stop words
# ============================================================

STOP_WORDS_EN = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "her",
    "was",
    "one",
    "our",
    "out",
    "has",
    "his",
    "how",
    "its",
    "may",
    "new",
    "now",
    "old",
    "see",
    "way",
    "who",
    "did",
    "yes",
    "yet",
    "able",
    "been",
    "came",
    "come",
    "done",
    "each",
    "find",
    "from",
    "give",
    "gone",
    "have",
    "here",
    "high",
    "into",
    "just",
    "know",
    "last",
    "like",
    "long",
    "look",
    "made",
    "make",
    "many",
    "more",
    "most",
    "much",
    "must",
    "need",
    "only",
    "open",
    "over",
    "page",
    "part",
    "play",
    "said",
    "same",
    "show",
    "some",
    "than",
    "that",
    "them",
    "then",
    "they",
    "this",
    "thus",
    "time",
    "took",
    "upon",
    "use",
    "very",
    "want",
    "well",
    "were",
    "what",
    "when",
    "where",
    "while",
    "will",
    "with",
    "would",
    "your",
    "about",
    "above",
    "after",
    "again",
    "also",
    "among",
    "back",
    "being",
    "below",
    "between",
    "both",
    "could",
    "doing",
    "down",
    "during",
    "even",
    "every",
    "first",
    "found",
    "great",
    "group",
    "having",
    "help",
    "home",
    "kind",
    "large",
    "later",
    "learn",
    "left",
    "less",
    "life",
    "little",
    "live",
    "lot",
    "main",
    "might",
    "mind",
    "near",
    "never",
    "next",
    "off",
    "often",
    "once",
    "other",
    "own",
    "people",
    "place",
    "point",
    "put",
    "read",
    "right",
    "room",
    "school",
    "seem",
    "side",
    "small",
    "sound",
    "start",
    "still",
    "study",
    "such",
    "take",
    "tell",
    "think",
    "till",
    "try",
    "turn",
    "until",
    "up",
    "upon",
    "us",
    "want",
    "water",
    "week",
    "went",
    "where",
    "whether",
    "without",
    "work",
    "year",
    "yet",
    "get",
    "got",
    "let",
    "set",
    "thing",
    "any",
    "few",
    "get",
    "got",
    "has",
    "had",
    "him",
    "them",
    "too",
    "try",
    "use",
    "via",
    "way",
    "won",
    "yet",
    "help",
    "please",
    "need",
    "want",
    "task",
    "job",
    "work",
    "thing",
    "stuff",
    "something",
    "anything",
    "everything",
    "nothing",
}

# Chinese stop words (2-char pairs that are too generic for matching)
STOP_WORDS_CN = {
    # Common verbs (generic actions, not domain-specific)
    "使用",
    "可以",
    "应该",
    "进行",
    "实现",
    "提供",
    "支持",
    "包括",
    "获取",
    "处理",
    "操作",
    "管理",
    "查看",
    "查询",
    "修改",
    "更新",
    "删除",
    "添加",
    "设置",
    "配置",
    "调用",
    "执行",
    "运行",
    "启动",
    "停止",
    "加载",
    "导入",
    "导出",
    "保存",
    "打开",
    "关闭",
    "选择",
    "确认",
    "检查",
    "验证",
    "测试",
    # Common pronouns/determiners
    "这个",
    "那个",
    "什么",
    "怎么",
    "如何",
    "是否",
    "能否",
    "请帮",
    "帮我",
    "帮忙",
    "我要",
    "我想",
    "想要",
    # Common generic nouns (too broad for skill matching)
    "内容",
    "信息",
    "功能",
    "方式",
    "方法",
    "结果",
    "问题",
    "情况",
    "状态",
    "类型",
    "字段",
    "参数",
    "选项",
    "步骤",
    "流程",
    "模式",
    "版本",
    "环境",
    # Common modifiers/conjunctions
    "一个",
    "一些",
    "所有",
    "全部",
    "部分",
    "其他",
    "另外",
    "当前",
    "本次",
    "以下",
    "以上",
    "之前",
    "之后",
    "如果",
    "因为",
    "所以",
    "但是",
    "不过",
    "而且",
    "或者",
    "以及",
    "还是",
    "就是",
    "这种",
    "那种",
    "这些",
    "那些",
    # 2-gram fragments that are pure noise
    "的数",
    "的表",
    "的文",
    "的格",
    "的报",
    "的图",
    "的音",
    "的视",
    "这份",
    "那个",
    "一个",
    "一份",
    "需要",
    "前去",
    "要去",
    # Generic descriptors (not domain-specific enough to be useful)
    "原始",
    "基础",
    "通用",
    "标准",
    "默认",
    "自动",
    "手动",
    "说明",
    "注意",
    "备注",
    # Task-bridging words that appear in both task and every skill
    "需要生",
    "适用",
    "用于",
    "用于",
    "的场",
    "不适用",
    "不涉",
}

# Pinyin stop words (romanized Chinese, too generic)
STOP_WORDS_PINYIN = {
    "shuju",
    "fenxi",
    "baogao",
    "wenjian",
    "biaoge",
    "biaoge",
    "mingling",
    "zidong",
    "shengcheng",
    "chakkan",
    "xiugai",
    "tianjia",
    "shanchu",
    "peizhi",
    "shezhi",
}


# ============================================================
# Session Manager: Interactive skill selection, tracking, review
# ============================================================


class SessionManager:
    """Manages active skill sessions: user selection, usage tracking, and
    periodic review to detect stale or low-value skills.

    State file (JSON) stores:
      - session_id: short identifier
      - created_at: ISO timestamp
      - task_desc: the original task description
      - active_skills: { skill_name: { activated_at, call_count, last_used_at, last_note } }
      - history: list of { action, skill, ts } entries
    """

    IDLE_THRESHOLD_SECONDS = 600  # 10 min unused -> candidate for removal
    MIN_CALLS_BEFORE_REVIEW = 2  # need at least N calls before judging efficiency
    LOW_USAGE_RATIO = 0.15  # calls / minutes_active < this -> low value

    def __init__(self, state_file=None):
        if state_file is None:
            state_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".session",
                "session_state.json",
            )
        self.state_file = state_file
        self.state = self._load_state()

    # ---- persistence ----

    def _load_state(self):
        """Load session state from disk, or create empty state."""
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "session_id": None,
            "created_at": None,
            "task_desc": "",
            "active_skills": {},
            "history": [],
        }

    def _save_state(self):
        """Persist state to disk."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    # ---- session lifecycle ----

    def start_session(self, task_desc, selected_skills):
        """Start a new session with user-selected skills.

        Args:
            task_desc: the task description string
            selected_skills: list of skill names the user chose
        Returns:
            dict: session summary
        """
        now = datetime.now().isoformat()
        self.state = {
            "session_id": now.replace(":", "").replace("-", "")[:14],
            "created_at": now,
            "task_desc": task_desc,
            "active_skills": {},
            "history": [],
        }
        for skill_name in selected_skills:
            self.state["active_skills"][skill_name] = {
                "activated_at": now,
                "call_count": 0,
                "last_used_at": None,
                "last_note": "",
            }
            self.state["history"].append(
                {"action": "activate", "skill": skill_name, "ts": now}
            )
        self._save_state()
        return self.get_status()

    def end_session(self):
        """End the current session, clearing all state."""
        old_id = self.state.get("session_id")
        self.state = {
            "session_id": None,
            "created_at": None,
            "task_desc": "",
            "active_skills": {},
            "history": [],
        }
        self._save_state()
        return old_id

    def is_active(self):
        """Check if a session is currently active."""
        return self.state.get("session_id") is not None

    # ---- skill management within session ----

    def activate(self, skill_name):
        """Add a skill to the active session."""
        if not self.is_active():
            return {"error": "No active session. Start a session first."}
        if skill_name in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is already active."}
        now = datetime.now().isoformat()
        self.state["active_skills"][skill_name] = {
            "activated_at": now,
            "call_count": 0,
            "last_used_at": None,
            "last_note": "",
        }
        self.state["history"].append(
            {"action": "activate", "skill": skill_name, "ts": now}
        )
        self._save_state()
        return {"activated": skill_name}

    def deactivate(self, skill_name, reason=""):
        """Remove a skill from the active session."""
        if not self.is_active():
            return {"error": "No active session."}
        if skill_name not in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is not active."}
        del self.state["active_skills"][skill_name]
        now = datetime.now().isoformat()
        self.state["history"].append(
            {
                "action": "deactivate",
                "skill": skill_name,
                "ts": now,
                "reason": reason,
            }
        )
        self._save_state()
        return {"deactivated": skill_name, "reason": reason}

    def track_usage(self, skill_name, note=""):
        """Record that a skill was used (called by the agent after each skill invocation).

        Args:
            skill_name: the skill that was used
            note: optional note about what it did (for efficiency review)
        Returns:
            dict: updated tracking info
        """
        if not self.is_active():
            return {"error": "No active session."}
        if skill_name not in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is not in active session."}
        info = self.state["active_skills"][skill_name]
        info["call_count"] += 1
        info["last_used_at"] = datetime.now().isoformat()
        if note:
            info["last_note"] = note
        self.state["history"].append(
            {
                "action": "track",
                "skill": skill_name,
                "ts": info["last_used_at"],
                "note": note,
            }
        )
        self._save_state()
        return {
            "skill": skill_name,
            "call_count": info["call_count"],
            "last_used_at": info["last_used_at"],
        }

    # ---- review & monitoring ----

    def review(self):
        """Analyze active skills and flag stale or low-value ones.

        Returns:
            dict with:
              - suggestions: list of { skill, reason, severity, detail }
              - healthy: list of skill names that are fine
              - summary: human-readable summary
        """
        if not self.is_active():
            return {"error": "No active session."}

        now = datetime.now()
        suggestions = []
        healthy = []
        active = self.state["active_skills"]

        if not active:
            return {
                "suggestions": [],
                "healthy": [],
                "summary": "No active skills in session.",
            }

        session_start = datetime.fromisoformat(self.state["created_at"])
        session_minutes = max((now - session_start).total_seconds() / 60.0, 1.0)

        for skill_name, info in active.items():
            call_count = info.get("call_count", 0)
            last_used_str = info.get("last_used_at")
            activated_str = info.get("activated_at", now.isoformat())

            # Never used
            if call_count == 0:
                activated_time = datetime.fromisoformat(activated_str)
                idle_since_activation = (now - activated_time).total_seconds()
                if idle_since_activation > self.IDLE_THRESHOLD_SECONDS:
                    suggestions.append(
                        {
                            "skill": skill_name,
                            "reason": "never_used",
                            "severity": "high",
                            "detail": (
                                f"Activated {int(idle_since_activation / 60)} min ago, "
                                f"never called once."
                            ),
                        }
                    )
                else:
                    suggestions.append(
                        {
                            "skill": skill_name,
                            "reason": "never_used",
                            "severity": "low",
                            "detail": (
                                f"Activated {int(idle_since_activation / 60)} min ago, "
                                f"not yet called (within grace period)."
                            ),
                        }
                    )
                continue

            # Used before but idle for too long
            if last_used_str:
                last_used = datetime.fromisoformat(last_used_str)
                idle_seconds = (now - last_used).total_seconds()
                if idle_seconds > self.IDLE_THRESHOLD_SECONDS:
                    suggestions.append(
                        {
                            "skill": skill_name,
                            "reason": "idle",
                            "severity": "medium",
                            "detail": (
                                f"Last used {int(idle_seconds / 60)} min ago "
                                f"({call_count} total calls)."
                            ),
                        }
                    )
                    continue

            # Low usage ratio (calls per minute)
            if call_count >= self.MIN_CALLS_BEFORE_REVIEW:
                usage_ratio = call_count / session_minutes
                if usage_ratio < self.LOW_USAGE_RATIO:
                    suggestions.append(
                        {
                            "skill": skill_name,
                            "reason": "low_efficiency",
                            "severity": "medium",
                            "detail": (
                                f"Only {call_count} calls in "
                                f"{int(session_minutes)} min "
                                f"(ratio {usage_ratio:.2f}/min)."
                            ),
                        }
                    )
                    continue

            healthy.append(skill_name)

        # Build summary
        lines = []
        if suggestions:
            lines.append(f"Found {len(suggestions)} skill(s) needing attention:")
            for s in suggestions:
                lines.append(f"  [{s['severity'].upper()}] {s['skill']}: {s['detail']}")
        else:
            lines.append("All active skills are healthy.")
        if healthy:
            lines.append(f"Healthy skills: {', '.join(healthy)}")

        return {
            "suggestions": suggestions,
            "healthy": healthy,
            "summary": "\n".join(lines),
        }

    # ---- status ----

    def get_status(self):
        """Get current session status."""
        if not self.is_active():
            return {"active": False, "message": "No active session."}
        active = self.state["active_skills"]
        now = datetime.now().isoformat()
        return {
            "active": True,
            "session_id": self.state["session_id"],
            "created_at": self.state["created_at"],
            "task_desc": self.state["task_desc"],
            "active_skills": {
                name: {
                    "call_count": info.get("call_count", 0),
                    "last_used_at": info.get("last_used_at"),
                    "activated_at": info.get("activated_at"),
                    "last_note": info.get("last_note", ""),
                }
                for name, info in active.items()
            },
            "skill_count": len(active),
        }


# ============================================================
# Interactive Selection
# ============================================================


def interactive_select(results, top_k=10):
    """Present matched skills to user for interactive selection.

    In a TTY environment, this would use numbered prompts.
    In a non-TTY (agent) environment, it outputs a structured selection
    format that the agent can parse and present to the user via
    the question tool.

    Args:
        results: list of match result dicts from SkillMatcher.match()
        top_k: max number of candidates to present
    Returns:
        dict with selection candidates for the agent to present
    """
    candidates = []
    for i, r in enumerate(results[:top_k], 1):
        candidates.append(
            {
                "index": i,
                "skill_name": r["skill_name"],
                "description": r.get("description", "")[:100],
                "score": r["score"],
                "confidence": r["recommendation"],
                "reasons": r.get("reasons", [])[:3],
                "path": r.get("path", ""),
            }
        )

    return {
        "action": "select_skills",
        "message": (
            "I found the following skills that match your task. "
            "Please select which ones to activate for this session:"
        ),
        "candidates": candidates,
        "instructions": (
            "Reply with skill names or indices (comma-separated), "
            "or 'all' to select all, or 'none' to skip."
        ),
    }


def parse_selection(user_input, candidates):
    """Parse user's selection response into a list of skill names.

    Accepts:
      - "all" -> all candidate skill names
      - "none" or "" -> empty list
      - "1,3,5" -> skills at those indices
      - "pdf,docx" -> skills by name
      - "1,3,pdf" -> mix of indices and names
    """
    user_input = user_input.strip().lower()
    if user_input == "all":
        return [c["skill_name"] for c in candidates]
    if user_input in ("none", "", "skip"):
        return []

    selected = []
    name_map = {c["skill_name"].lower(): c["skill_name"] for c in candidates}

    for part in user_input.split(","):
        part = part.strip()
        if not part:
            continue
        # Try as index
        if part.isdigit():
            idx = int(part)
            for c in candidates:
                if c["index"] == idx:
                    selected.append(c["skill_name"])
                    break
        # Try as name
        elif part in name_map:
            selected.append(name_map[part])
        # Fuzzy name match
        else:
            for c in candidates:
                if part in c["skill_name"].lower():
                    selected.append(c["skill_name"])
                    break

    # Deduplicate preserving order
    seen = set()
    result = []
    for s in selected:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def format_report(results, task_description, scan_count, elapsed_ms, verbose=False):
    """Format match results as a readable report."""
    lines = []
    lines.append("=" * 70)
    lines.append("SKILL ROUTER - Match Report")
    lines.append("=" * 70)
    lines.append(f"Task: {task_description}")
    lines.append(f"Scanned: {scan_count} skills in {elapsed_ms:.0f}ms")
    lines.append(f"Matched: {len(results)} skills above threshold")
    lines.append("-" * 70)

    if not results:
        lines.append("No matching skills found.")
        lines.append("")
        lines.append("Possible reasons:")
        lines.append("  1. No skill installed for this task type")
        lines.append("  2. Task description too vague - add more keywords")
        lines.append("  3. Run with --refresh to rebuild the skill index")
        lines.append("")
        lines.append("Run 'python skill_router.py --list' to see all installed skills.")
        return "\n".join(lines)

    for i, r in enumerate(results, 1):
        marker = ">>>" if i == 1 else "   "
        lines.append(f"{marker} #{i}  [{r['recommendation']}]  score={r['score']}")
        lines.append(f"    Name: {r['skill_name']}")
        lines.append(f"    Desc: {r['description'][:120]}")
        if r["tools"]:
            lines.append(f"    Tools: {', '.join(r['tools'][:5])}")
        if verbose:
            lines.append(f"    Path: {r['path']}")
            for reason in r["reasons"][:8]:
                lines.append(f"    -> {reason}")
        lines.append("")

    # Recommendation
    if results:
        top = results[0]
        lines.append("-" * 70)
        lines.append(f"RECOMMENDED: Load skill '{top['skill_name']}'")
        lines.append(f"  Load command: skill({top['skill_name']})")
        lines.append(f"  Confidence: {top['recommendation']} (score={top['score']})")
        if len(results) >= 2:
            second = results[1]
            lines.append(
                f"  Alternative: {second['skill_name']} (score={second['score']})"
            )
        lines.append("=" * 70)

    return "\n".join(lines)


def format_json(results, task_description, scan_count, elapsed_ms):
    """Format match results as JSON."""
    return json.dumps(
        {
            "task": task_description,
            "scanned": scan_count,
            "elapsed_ms": round(elapsed_ms, 1),
            "matched": len(results),
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Skill Router - Find, select, and manage skills for your task",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic matching
  python skill_router.py "write a novel chapter"
  python skill_router.py "create a PDF report" --json
  python skill_router.py "analyze Excel data" --top 5 --verbose

  # Interactive session
  python skill_router.py "build a website" --select
  python skill_router.py --start "build a website" --skills frontend-design,python
  python skill_router.py --status
  python skill_router.py --track frontend-design --note "generated component"
  python skill_router.py --review
  python skill_router.py --deactivate frontend-design --reason "no longer needed"
  python skill_router.py --end

  # Index management
  python skill_router.py --list
  python skill_router.py --refresh
        """,
    )
    parser.add_argument("task", nargs="?", help="Task description to match")
    parser.add_argument("--task-file", "-f", help="Read task description from file")
    parser.add_argument(
        "--top", "-k", type=int, default=10, help="Top K results (default: 10)"
    )
    parser.add_argument(
        "--min-score", type=float, default=15, help="Minimum match score (default: 15)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show match details"
    )
    parser.add_argument("--list", action="store_true", help="List all installed skills")
    parser.add_argument(
        "--refresh", action="store_true", help="Force rebuild skill index cache"
    )
    parser.add_argument("--blacklist", help="Comma-separated skill names to exclude")
    parser.add_argument("--skill-root", help="Override skill root directory")

    # Session management args
    parser.add_argument(
        "--select",
        action="store_true",
        help="After matching, output interactive selection prompt (for agent to present to user)",
    )
    parser.add_argument(
        "--start",
        metavar="TASK_DESC",
        help="Start a new skill session with a task description",
    )
    parser.add_argument(
        "--skills",
        help="Comma-separated skill names to activate with --start",
    )
    parser.add_argument(
        "--activate",
        metavar="SKILL_NAME",
        help="Activate a skill in the current session",
    )
    parser.add_argument(
        "--deactivate",
        metavar="SKILL_NAME",
        help="Deactivate a skill from the current session",
    )
    parser.add_argument(
        "--track",
        metavar="SKILL_NAME",
        help="Record usage of a skill in the current session",
    )
    parser.add_argument("--note", help="Note to attach to --track or --deactivate")
    parser.add_argument(
        "--status", action="store_true", help="Show current session status"
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review active skills for stale or low-value ones",
    )
    parser.add_argument("--end", action="store_true", help="End the current session")

    args = parser.parse_args()

    # Override skill root if provided
    if args.skill_root:
        global SKILL_ROOT_CANDIDATES
        SKILL_ROOT_CANDIDATES = [args.skill_root]

    # Build blacklist
    blacklist = list(DEFAULT_BLACKLIST)
    if args.blacklist:
        blacklist.extend([s.strip() for s in args.blacklist.split(",")])

    # Create index
    index = SkillIndex(blacklist=blacklist)
    session = SessionManager()

    # ---- --list mode ----
    if args.list:
        count = index.build_index(use_cache=True, force_refresh=args.refresh)
        print(f"Installed skills ({count}):")
        print("-" * 60)
        for name in sorted(index.skills.keys()):
            info = index.skills[name]
            desc = info.get("description", "")[:80]
            tier = info.get("tier", "?")
            print(f"  [{tier:8s}] {name:30s} {desc}")
        return

    # ---- --refresh mode ----
    if args.refresh and not args.task:
        count = index.build_index(force_refresh=True)
        print(f"Skill index rebuilt: {count} skills indexed.")
        print(f"Cache: {CACHE_FILE}")
        return

    # ---- Session management ----
    if args.status:
        status = session.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    if args.start:
        skills = []
        if args.skills:
            skills = [s.strip() for s in args.skills.split(",") if s.strip()]
        result = session.start_session(args.start, skills)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.activate:
        result = session.activate(args.activate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.deactivate:
        reason = args.note or ""
        result = session.deactivate(args.deactivate, reason=reason)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.track:
        note = args.note or ""
        result = session.track_usage(args.track, note=note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.review:
        result = session.review()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.end:
        old_id = session.end_session()
        if old_id:
            print(json.dumps({"ended": old_id}, ensure_ascii=False))
        else:
            print(
                json.dumps({"error": "No active session to end."}, ensure_ascii=False)
            )
        return

    # ---- Default: match task ----
    task = args.task or ""
    if args.task_file:
        try:
            with open(args.task_file, "r", encoding="utf-8") as f:
                task = f.read().strip()
        except Exception as e:
            print(f"Error reading task file: {e}", file=sys.stderr)
            sys.exit(1)

    if not task:
        parser.print_help()
        sys.exit(1)

    # Build index
    count = index.build_index(use_cache=True, force_refresh=args.refresh)
    if count == 0:
        print("No skills found. Check your skill installation directory.")
        print(f"Searched roots: {index.skill_roots}")
        sys.exit(1)

    # Match
    matcher = SkillMatcher(index)
    t0 = time.time()
    results = matcher.match(
        task, top_k=args.top, min_score=args.min_score, verbose=args.verbose
    )
    elapsed_ms = (time.time() - t0) * 1000

    # --select mode: output interactive selection prompt as JSON
    if args.select:
        selection = interactive_select(results, top_k=args.top)
        print(json.dumps(selection, ensure_ascii=False, indent=2))
        return

    # Default output
    if args.json:
        print(format_json(results, task, count, elapsed_ms))
    else:
        print(format_report(results, task, count, elapsed_ms, verbose=args.verbose))


if __name__ == "__main__":
    main()
