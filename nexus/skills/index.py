"""SkillIndex: scan and parse SKILL.md files.

Port of skill-router's SkillIndex class with all original methods:
- _find_skill_roots
- _find_skill_dirs
- _parse_skill_md
- _extract_keywords
- build_index
- _cache_signature
- _save_cache
- _load_cache
"""

from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from nexus.skills.constants import (
    CATEGORY_KEYWORDS,
    CN_EN_KEYWORD_MAP,
    DEFAULT_BLACKLIST,
    SKILL_NAME_ALIASES,
    SKILL_ROOT_CANDIDATES,
    SKILL_SUBDIRS,
)

log = logging.getLogger(__name__)


class SkillIndex:
    """Scans skill directories, parses SKILL.md files, builds searchable index."""

    def __init__(self, skill_roots=None, blacklist=None):
        self.skill_roots = skill_roots or self._find_skill_roots()
        self.blacklist = set(blacklist or DEFAULT_BLACKLIST)
        self.skills = {}
        self._cache_valid = False

    def _find_skill_roots(self):
        """Auto-discover skill root directories."""
        roots = set()
        for pattern in SKILL_ROOT_CANDIDATES:
            if not pattern:
                continue
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
                        skill_dirs.append({
                            "name": entry,
                            "path": skill_path,
                            "skill_md": skill_md,
                            "tier": subdir or "root",
                        })
        return skill_dirs

    def _extract_keywords(self, text):
        """Extract meaningful keywords from text (both Chinese and English)."""
        keywords = set()

        en_words = re.findall(
            r"(?:^|[\s\u4e00-\u9fff,;:!?()\"'\[\]{}|/\\])([a-zA-Z]{2,}[0-9a-zA-Z]*)",
            text,
        )
        en_words += re.findall(r"\b([a-zA-Z]{2,}[0-9a-zA-Z]*)\b", text)
        for w in en_words:
            w_lower = w.lower()
            if w_lower not in STOP_WORDS_EN and len(w_lower) >= 2:
                keywords.add(w_lower)

        cn_segments = re.findall(r"[\u4e00-\u9fff]+", text)
        for seg in cn_segments:
            if len(seg) >= 2:
                if len(seg) <= 6 and seg not in STOP_WORDS_CN:
                    keywords.add(seg)
                for i in range(len(seg) - 1):
                    gram = seg[i:i + 2]
                    if gram not in STOP_WORDS_CN:
                        keywords.add(gram)
                if len(seg) >= 3:
                    for i in range(len(seg) - 2):
                        gram = seg[i:i + 3]
                        if gram not in STOP_WORDS_CN:
                            keywords.add(gram)

        extra = set()
        for kw in keywords:
            if kw in CN_EN_KEYWORD_MAP:
                for en_word in CN_EN_KEYWORD_MAP[kw]:
                    extra.add(en_word.lower())
        keywords |= extra

        return list(keywords)

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
            "no_triggers": [],
            "tools": [],
            "raw_text": content[:8000],
            "full_length": len(content),
        }

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            name_match = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
            if name_match:
                info["name"] = name_match.group(1).strip().strip("\"'")

            desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
            if desc_match:
                first_line = desc_match.group(1).strip().strip("\"'")
                if first_line in (">", "|", ">-", "|-", ">", "|"):
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

        if not info["name"]:
            h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if h1_match:
                name = h1_match.group(1).strip()
                name = re.sub(r"^Skill:\s*", "", name, flags=re.IGNORECASE)
                info["name"] = name

        if not info["description"]:
            lines = content.split("\n")
            for line in lines[1:20]:
                line = line.strip()
                if (line and not line.startswith("#") and
                        not line.startswith("---") and len(line) > 15):
                    info["description"] = line[:300]
                    break

        # Extract trigger keywords
        trigger_patterns = [
            r"(?:触发词|触发关键词|关键词)\s*[:：]\s*(.+)",
            r"(?:Triggers?|TRIGGER)\s*[:：]\s*(.+)",
        ]
        for pattern in trigger_patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            for m in matches:
                items = re.split(r"[,;|，；、]+", m)
                for item in items:
                    item = item.strip().strip('"\'""[]()（）「」『』')
                    if item and 2 <= len(item) <= 30:
                        info["triggers"].append(item)

        scene_pattern = r"(?:触发场景|适用场景|何时使用|When to use|Use when)\s*[:：]?\s*\n((?:.*\n)*?)(?=\n#|\n##|\Z)"
        scene_match = re.search(scene_pattern, content, re.IGNORECASE)
        if scene_match:
            scene_text = scene_match.group(1)
            bullets = re.findall(r"^[\-\*]\s*(.+)", scene_text, re.MULTILINE)
            for b in bullets:
                b = b.strip().strip('"\'""[]()（）「」『』')
                if len(b) > 30:
                    parts = re.split(r"[，。；,;.]", b)
                    b = parts[0].strip()
                if b and 2 <= len(b) <= 30:
                    info["triggers"].append(b)

        info["triggers"] = list(dict.fromkeys(info["triggers"]))

        # Extract DO NOT TRIGGER patterns
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

        # Extract tool/method names
        tool_pattern = re.findall(
            r'(?:python|bash|node)\s+["\']?[^/]+/(\w+)\.py["\']?\s+(\w+)', content
        )
        for script_name, method_name in tool_pattern:
            info["tools"].append(method_name)

        call_sections = re.findall(
            r"调用方式\s*[:：]\s*(.*?)(?=\n###|\n##|\n#|\Z)", content, re.DOTALL
        )
        for section in call_sections:
            tool_match = re.search(r'(\w+)\.py["\']?\s+(\w+)', section)
            if tool_match:
                info["tools"].append(tool_match.group(2))

        info["tools"] = list(dict.fromkeys(info["tools"]))

        keyword_text = (
            info["description"] + " " + " ".join(info["triggers"]) + " " + info["name"]
        )
        info["keywords"] = self._extract_keywords(keyword_text)

        return info

    def build_index(self, use_cache=True, force_refresh=False):
        """Scan all skill directories and build the search index."""
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
                info["dir_name"] = name
                info["keywords"] = self._extract_keywords(info.get("description", ""))
                self.skills[name] = info

        self._save_cache()
        self._cache_valid = True
        return len(self.skills)

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
        """Save index to JSON cache file."""
        try:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
            os.makedirs(cache_dir, exist_ok=True)
            sig = self._cache_signature()
            data = {
                "signature": sig,
                "skills": self.skills,
                "built_at": datetime.now().isoformat(),
            }
            cache_file = os.path.join(cache_dir, "skill_index.json")
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_cache(self):
        """Load index from JSON cache if still valid."""
        try:
            cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "skill_index.json")
            if not os.path.isfile(cache_file):
                return False
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            current_sig = self._cache_signature()
            if data.get("signature") != current_sig:
                return False
            self.skills = data.get("skills", {})
            self._cache_valid = True
            return True
        except Exception:
            return False


# Stop words needed by matcher - import-safe re-exports
STOP_WORDS_EN = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
    "was", "one", "our", "out", "has", "his", "how", "its", "may", "new",
    "now", "old", "see", "way", "who", "did", "yes", "yet", "able", "been",
    "came", "come", "done", "each", "find", "from", "give", "gone", "have",
    "here", "high", "into", "just", "know", "last", "like", "long", "look",
    "made", "make", "many", "more", "most", "much", "must", "need", "only",
    "open", "over", "page", "part", "play", "said", "same", "show", "some",
    "than", "that", "them", "then", "they", "this", "thus", "time", "took",
    "upon", "use", "very", "want", "well", "were", "what", "when", "where",
    "while", "will", "with", "would", "your", "about", "above", "after",
    "again", "also", "among", "back", "being", "below", "between", "both",
    "could", "doing", "down", "during", "even", "every", "first", "found",
    "great", "group", "having", "help", "home", "kind", "large", "later",
    "learn", "left", "less", "life", "little", "live", "lot", "main", "might",
    "mind", "near", "never", "next", "off", "often", "once", "other", "own",
    "people", "place", "point", "put", "read", "right", "room", "school",
    "seem", "side", "small", "sound", "start", "still", "study", "such",
    "take", "tell", "think", "till", "try", "turn", "until", "up", "upon",
    "us", "want", "water", "week", "went", "where", "whether", "without",
    "work", "year", "yet", "get", "got", "let", "set", "thing", "any", "few",
    "get", "got", "has", "had", "him", "them", "too", "try", "use", "via",
    "way", "won", "yet", "help", "please", "need", "want", "task", "job",
    "work", "thing", "stuff", "something", "anything", "everything", "nothing",
}

STOP_WORDS_CN = {
    "使用", "可以", "应该", "进行", "实现", "提供", "支持", "包括",
    "获取", "处理", "操作", "管理", "查看", "查询", "修改", "更新",
    "删除", "添加", "设置", "配置", "调用", "执行", "运行", "启动",
    "停止", "加载", "导入", "导出", "保存", "打开", "关闭", "选择",
    "确认", "检查", "验证", "测试",
    "这个", "那个", "什么", "怎么", "如何", "是否", "能否", "请帮",
    "帮我", "帮忙", "我要", "我想", "想要",
    "内容", "信息", "功能", "方式", "方法", "结果", "问题", "情况",
    "状态", "类型", "字段", "参数", "选项", "步骤", "流程", "模式",
    "版本", "环境",
    "一个", "一些", "所有", "全部", "部分", "其他", "另外", "当前",
    "本次", "以下", "以上", "之前", "之后", "如果", "因为", "所以",
    "但是", "不过", "而且", "或者", "以及", "还是", "就是", "这种",
    "那种", "这些", "那些",
    "的数", "的表", "的文", "的格", "的报", "的图", "的音", "的视",
    "这份", "那个", "一个", "一份", "需要", "前去", "要去",
    "原始", "基础", "通用", "标准", "默认", "自动", "手动", "说明",
    "注意", "备注",
    "需要生", "适用", "用于", "用于", "的场", "不适用", "不涉",
}

STOP_WORDS_PINYIN = {
    "shuju", "fenxi", "baogao", "wenjian", "biaoge", "biaoge",
    "mingling", "zidong", "shengcheng", "chakkan", "xiugai", "tianjia",
    "shanchu", "peizhi", "shezhi",
}
