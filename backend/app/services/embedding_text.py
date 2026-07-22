from pathlib import Path


def build_embedding_text(
    *,
    file_name: str,
    text: str,
    section_title: str | None = None,
) -> str:
    title = Path(file_name).stem.strip() or file_name.strip() or "未命名文档"
    parts = [f"文档：{title}"]
    if section_title and section_title.strip():
        parts.append(f"章节：{section_title.strip()}")
    parts.append(f"内容：{text.strip()}")
    return "\n".join(parts)
