from html.parser import HTMLParser
from pathlib import Path

from docx import Document as DocxDocument
from markdown import markdown
from pypdf import PdfReader

from app.services.text_splitter import TextBlock


class DocumentParseError(ValueError):
    """文档内容无法被解析。"""


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}:
            self.parts.append("\n")

    def get_text(self) -> str:
        return " ".join(part for part in self.parts if part != "\n").strip()


class DocumentParser:
    supported_types = {"pdf", "docx", "md", "markdown", "txt"}

    def parse(self, file_path: str, file_type: str) -> list[TextBlock]:
        path = Path(file_path)
        normalized_type = file_type.lower().lstrip(".")

        try:
            if normalized_type == "pdf":
                blocks = self._parse_pdf(path)
            elif normalized_type == "docx":
                blocks = self._parse_docx(path)
            elif normalized_type in {"md", "markdown"}:
                blocks = [TextBlock(text=self._parse_markdown(path))]
            elif normalized_type == "txt":
                blocks = [TextBlock(text=self._read_text(path))]
            else:
                raise DocumentParseError(f"不支持的文档格式：{file_type}。")
        except DocumentParseError:
            raise
        except FileNotFoundError as exc:
            raise DocumentParseError("文档解析失败：找不到已上传的文件，请重新上传。") from exc
        except Exception as exc:
            raise DocumentParseError(
                "文档解析失败：文件可能已损坏、被加密或内容格式不正确。"
            ) from exc

        if not any(block.text.strip() for block in blocks):
            raise DocumentParseError(
                "文档解析失败：未提取到可用文字；扫描版 PDF 请先进行 OCR 识别。"
            )
        return blocks

    def _parse_pdf(self, path: Path) -> list[TextBlock]:
        reader = PdfReader(str(path))
        blocks: list[TextBlock] = []

        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                blocks.append(TextBlock(text=text, page_no=page_index))

        return blocks

    def _parse_docx(self, path: Path) -> list[TextBlock]:
        document = DocxDocument(str(path))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]

        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if values:
                    paragraphs.append(" | ".join(values))

        return [TextBlock(text="\n".join(paragraphs))]

    def _parse_markdown(self, path: Path) -> str:
        raw = self._read_text(path)
        html = markdown(raw)
        extractor = _HtmlTextExtractor()
        extractor.feed(html)
        extracted = extractor.get_text()
        return extracted or raw

    def _read_text(self, path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")


document_parser = DocumentParser()
