"""Deterministic exhaustive-scope requests, separate from terminology questions."""
import re


def requires_research(question):
    text = re.sub(r'"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|《[^》\n]*》', "", question).casefold()
    scope = r"(?:所有论文|全部论文|每篇论文|所有文献|全部文献|每篇文献|全库|整库)"
    action = r"(?:总结|汇总|综合|比较|对比|逐篇|逐一|审查|检查|分析|研究|提取|列出|共同|结论|贡献|方法|结果)"
    return bool(
        re.search(action + r".{0,18}" + scope, text)
        or re.search(scope + r".{0,24}" + action, text)
        or re.fullmatch(scope + r"[？?\s]*", text)
        or re.search(r"\b(?:summari[sz]e|review|compare|analy[sz]e|evaluate|extract|check|survey|assess|list|synthesi[sz]e|across)\b.{0,50}\b(?:all|every|each)\s+(?:selected\s+)?papers?\b", text)
        or re.search(r"\b(?:in|across|from)\s+(?:all|every|each)\s+(?:selected\s+)?papers?\b", text)
        or re.search(r"\b(?:all|every|each)\s+(?:selected\s+)?papers?\b.{0,40}\b(?:conclude|show|report|agree|support|demonstrate)\b", text)
    )
