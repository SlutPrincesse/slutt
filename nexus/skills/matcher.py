"""Skill matching: 7-layer relevance scoring.

Port of skill-router's SkillMatcher class with all original layers:
L0 - Name match (50 pts)
L0b - Alias match (45 pts)
L1 - Trigger match (x2 weight)
L2 - Description overlap (x2 weight)
L3 - Fuzzy text search (x1 weight)
L4 - Category boost (x1.5 weight)
L5 - Negative filter (-20 penalty)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from nexus.skills.constants import (
    CATEGORY_KEYWORDS,
    CN_EN_KEYWORD_MAP,
    SKILL_NAME_ALIASES,
)

log = logging.getLogger(__name__)

# Stop words are imported from constants where needed
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


class SkillMatcher:
    """Matches a task description against the skill index using multi-layer scoring."""

    def __init__(self, index):
        self.index = index

    def match(self, task_description, top_k=10, min_score=15, verbose=False):
        """Match task description against all skills."""
        results = []
        task_lower = task_description.lower()

        task_keywords = self._extract_task_keywords(task_description)
        task_categories = self._detect_category(task_description)

        if verbose:
            import sys as _sys
            print(f"[debug] Task keywords: {task_keywords}", file=_sys.stderr)
            print(f"[debug] Task categories: {task_categories}", file=_sys.stderr)

        for skill_name, skill_info in self.index.skills.items():
            score = 0
            match_reasons = []

            # Layer 0: Skill name direct match
            dir_name = skill_info.get("dir_name", skill_name).lower()
            display_name = skill_info.get("name", skill_name).lower()
            for sname in [dir_name, display_name]:
                if len(sname) >= 3 and sname in task_lower:
                    score += 50.0
                    match_reasons.append(f"name_match: '{sname}'")
                    break

            # Layer 0b: Alias match
            aliases = SKILL_NAME_ALIASES.get(skill_info.get("dir_name", skill_name), [])
            for alias in aliases:
                if alias in task_description:
                    score += 45.0
                    match_reasons.append(f"alias_match: '{alias}'")
                    break

            # Layer 1: Trigger keyword match
            trigger_score, trigger_hits = self._score_triggers(task_keywords, skill_info)
            if trigger_score > 0:
                score += trigger_score * 2.0
                for hit in trigger_hits:
                    match_reasons.append(f"trigger: '{hit}'")

            # Layer 2: Description keyword overlap
            desc_score, desc_hits = self._score_description_overlap(task_keywords, skill_info)
            if desc_score > 0:
                score += desc_score * 2.0
                for hit in desc_hits:
                    match_reasons.append(f"keyword: '{hit}'")

            # Layer 3: Fuzzy text search
            fuzzy_score, fuzzy_hits = self._score_fuzzy_text(task_keywords, skill_info)
            if fuzzy_score > 0:
                score += fuzzy_score * 1.0
                for hit in fuzzy_hits[:3]:
                    match_reasons.append(f"fuzzy: '{hit}'")

            # Layer 4: Category boost
            if task_categories:
                cat_score = self._score_category_boost(task_categories, skill_info)
                if cat_score > 0:
                    score += cat_score * 1.5
                    match_reasons.append(f"category: {', '.join(task_categories)}")

            # Layer 5: Negative filter
            negative_hits = self._check_negative_filters(task_keywords, skill_info)
            if negative_hits:
                score -= 20
                for hit in negative_hits:
                    match_reasons.append(f"NEGATIVE: '{hit}'")

            if score >= min_score:
                results.append({
                    "skill_name": skill_info.get("dir_name", skill_name),
                    "display_name": skill_info.get("name", skill_name),
                    "description": skill_info.get("description", "")[:200],
                    "score": round(score, 2),
                    "tier": skill_info.get("tier", "unknown"),
                    "path": skill_info.get("path", ""),
                    "tools": skill_info.get("tools", []),
                    "reasons": match_reasons,
                    "recommendation": self._make_recommendation(score),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _extract_task_keywords(self, task_description):
        """Extract keywords from the user's task description."""
        keywords = set()
        text = task_description.lower()

        en_words = re.findall(
            r"(?:^|[\s\u4e00-\u9fff,;:!?()\"'\[\]{}|/\\])([a-zA-Z]{2,}[0-9a-zA-Z]*)",
            task_description,
        )
        en_words += re.findall(r"\b([a-zA-Z]{2,}[0-9a-zA-Z]*)\b", text)
        for w in en_words:
            w_lower = w.lower()
            if w_lower not in STOP_WORDS_EN:
                keywords.add(w_lower)

        cn_segments = re.findall(r"[\u4e00-\u9fff]+", task_description)
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
                    continue
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
