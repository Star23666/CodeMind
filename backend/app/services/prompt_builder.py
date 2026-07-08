from app.schemas.contracts import SourceReference


MAX_SOURCE_CHARS = 900


def truncate_source_text(text: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars]}..."


def build_rag_prompt(
    *,
    question: str,
    rewritten_question: str | None,
    sources: list[SourceReference],
) -> str:
    source_block = build_source_block(sources)
    rewritten_block = f"\n检索问题：\n{rewritten_question}\n" if rewritten_question else ""

    return f"""你是 CodeMind 的计算机知识问答助手。
请只根据给定资料回答问题，不要编造资料外结论。
如果资料不足，请明确说明“知识库中未找到足够依据”。
回答要求：
1. 先直接回答问题，再补充必要解释。
2. 关键结论后标注来源编号，例如 [来源1]。
3. 不要输出与问题无关的长篇背景。

用户原始问题：
{question}
{rewritten_block}
参考资料：
{source_block}

请生成最终回答："""


def build_source_block(sources: list[SourceReference]) -> str:
    if not sources:
        return "未检索到可用资料。"

    lines = []
    for index, source in enumerate(sources, start=1):
        page = f"第 {source.page_no} 页" if source.page_no is not None else "页码未知"
        score = f"{source.score:.6f}" if source.score is not None else "无"
        lines.append(
            "\n".join(
                [
                    f"[来源{index}]",
                    f"文件：{source.file_name}",
                    f"位置：chunk_id={source.chunk_id}，chunk_index={source.chunk_index}，{page}",
                    f"相关度：{score}",
                    f"内容：{truncate_source_text(source.source_text)}",
                ]
            )
        )
    return "\n\n".join(lines)

