from dataclasses import dataclass


@dataclass(frozen=True)
class TextBlock:
    text: str
    page_no: int | None = None
    section_title: str | None = None


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    page_no: int | None
    start_offset: int
    end_offset: int
    section_title: str | None = None


class TextSplitter:
    def __init__(self, *, chunk_size: int = 800, overlap: int = 120) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split_blocks(self, blocks: list[TextBlock]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        document_offset = 0

        for block in blocks:
            text = self._normalize_text(block.text)
            if not text:
                continue

            for start, end in self._window_ranges(text):
                chunk_text = text[start:end].strip()
                if not chunk_text:
                    continue

                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        text=chunk_text,
                        page_no=block.page_no,
                        start_offset=document_offset + start,
                        end_offset=document_offset + end,
                        section_title=block.section_title,
                    )
                )

            document_offset += len(text) + 2

        return chunks

    def _window_ranges(self, text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        start = 0
        text_length = len(text)

        while start < text_length:
            hard_end = min(start + self.chunk_size, text_length)
            end = self._find_natural_break(text, start, hard_end)
            ranges.append((start, end))

            if end >= text_length:
                break

            start = max(end - self.overlap, start + 1)

        return ranges

    def _find_natural_break(self, text: str, start: int, hard_end: int) -> int:
        if hard_end >= len(text):
            return hard_end

        window = text[start:hard_end]
        break_chars = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";"]
        best = -1

        for char in break_chars:
            index = window.rfind(char)
            if index > best:
                best = index + len(char)

        min_usable = int(self.chunk_size * 0.55)
        if best >= min_usable:
            return start + best
        return hard_end

    def _normalize_text(self, text: str) -> str:
        lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        normalized_lines: list[str] = []

        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank:
                    normalized_lines.append("")
                previous_blank = True
                continue

            normalized_lines.append(line)
            previous_blank = False

        return "\n".join(normalized_lines).strip()


text_splitter = TextSplitter()
