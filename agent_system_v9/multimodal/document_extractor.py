"""
Document Extractor - Unified binary parser converting PDFs, images, and sheets to structured JSON
"""
import base64
import csv
import io
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO


class DocumentType(Enum):
    PDF = "pdf"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    TEXT = "text"
    HTML = "html"
    WORD = "word"
    POWERPOINT = "powerpoint"
    UNKNOWN = "unknown"


@dataclass
class ExtractedContent:
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    document_id: str
    document_type: DocumentType
    filename: str
    content: ExtractedContent
    pages: int = 0
    size_bytes: int = 0
    extraction_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DocumentExtractor:
    def __init__(self):
        self._parsers: dict[DocumentType, Callable] = {}
        self._lock = threading.RLock()
        self._register_default_parsers()

    def _register_default_parsers(self):
        self._parsers[DocumentType.PDF] = self._parse_pdf
        self._parsers[DocumentType.IMAGE] = self._parse_image
        self._parsers[DocumentType.SPREADSHEET] = self._parse_spreadsheet
        self._parsers[DocumentType.TEXT] = self._parse_text
        self._parsers[DocumentType.HTML] = self._parse_html
        self._parsers[DocumentType.WORD] = self._parse_word
        self._parsers[DocumentType.POWERPOINT] = self._parse_powerpoint

    def extract(self, file_data: bytes | BinaryIO | str,
                filename: str = "", document_type: DocumentType = None) -> ExtractedDocument:
        start_time = time.time()

        # Read file data
        if isinstance(file_data, str):
            # Path
            path = Path(file_data)
            with Path(path).open('rb') as f:
                data = f.read()
            filename = filename or path.name
        elif hasattr(file_data, 'read'):
            data = file_data.read()
        else:
            data = file_data

        # Detect type if not provided
        if document_type is None:
            document_type = self._detect_type(data, filename)

        document_id = f"doc_{hash(data) % 10000000}"

        # Parse
        parser = self._parsers.get(document_type)
        if not parser:
            return ExtractedDocument(
                document_id=document_id,
                document_type=document_type,
                filename=filename,
                content=ExtractedContent(),
                size_bytes=len(data),
                extraction_time=time.time() - start_time,
                errors=[f"No parser for {document_type.value}"]
            )

        try:
            content = parser(data)
            errors = content.metadata.pop("_errors", [])
            warnings = content.metadata.pop("_warnings", [])

            return ExtractedDocument(
                document_id=document_id,
                document_type=document_type,
                filename=filename,
                content=content,
                pages=content.metadata.get("pages", 0),
                size_bytes=len(data),
                extraction_time=time.time() - start_time,
                errors=errors,
                warnings=warnings
            )
        except Exception as e:
            return ExtractedDocument(
                document_id=document_id,
                document_type=document_type,
                filename=filename,
                content=ExtractedContent(),
                size_bytes=len(data),
                extraction_time=time.time() - start_time,
                errors=[str(e)]
            )

    def extract_batch(self, files: list[bytes | BinaryIO | str],
                      filenames: list[str] = None) -> list[ExtractedDocument]:
        results = []
        for i, file_data in enumerate(files):
            filename = filenames[i] if filenames and i < len(filenames) else f"file_{i}"
            results.append(self.extract(file_data, filename))
        return results

    def _detect_type(self, data: bytes, filename: str) -> DocumentType:
        # Check magic bytes
        if data.startswith(b'%PDF'):
            return DocumentType.PDF
        if data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff') or data.startswith(b'GIF8'):
            return DocumentType.IMAGE
        if data.startswith(b'PK\x03\x04'):  # ZIP-based formats
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                return DocumentType.SPREADSHEET
            if filename.endswith('.docx'):
                return DocumentType.WORD
            if filename.endswith('.pptx'):
                return DocumentType.POWERPOINT
        elif filename.endswith('.pdf'):
            return DocumentType.PDF
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff')):
            return DocumentType.IMAGE
        elif filename.endswith(('.xlsx', '.xls', '.csv', '.ods')):
            return DocumentType.SPREADSHEET
        elif filename.endswith(('.txt', '.md', '.rst', '.log')):
            return DocumentType.TEXT
        elif filename.endswith(('.html', '.htm')):
            return DocumentType.HTML
        elif filename.endswith(('.docx', '.doc')):
            return DocumentType.WORD
        elif filename.endswith(('.pptx', '.ppt')):
            return DocumentType.POWERPOINT

        return DocumentType.UNKNOWN

    def _parse_pdf(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []
        warnings = []

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=data, filetype="pdf")
            content.metadata["pages"] = len(doc)

            texts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                texts.append(page.get_text())

                # Extract tables
                tabs = page.find_tables()
                for table in tabs:
                    table_data = table.extract()
                    if table_data:
                        content.tables.append(table_data)

                # Extract images
                for img in page.get_images():
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n < 5:
                        img_data = pix.tobytes("png")
                        content.images.append({
                            "page": page_num,
                            "xref": xref,
                            "width": pix.width,
                            "height": pix.height,
                            "data": base64.b64encode(img_data).decode()
                        })

            content.text = "\n\n".join(texts)
            doc.close()

        except ImportError:
            errors.append("PyMuPDF (fitz) not installed")
        except Exception as e:
            errors.append(f"PDF parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        content.metadata["_warnings"] = warnings
        return content

    def _parse_image(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []
        warnings = []

        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            content.metadata["width"] = img.width
            content.metadata["height"] = img.height
            content.metadata["format"] = img.format
            content.metadata["mode"] = img.mode

            # OCR would go here
            content.text = f"[Image: {img.format} {img.width}x{img.height}]"

            # Store image data
            content.images.append({
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "data": base64.b64encode(data).decode()
            })

        except ImportError:
            errors.append("PIL/Pillow not installed")
        except Exception as e:
            errors.append(f"Image parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        content.metadata["_warnings"] = warnings
        return content

    def _parse_spreadsheet(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []
        warnings = []

        try:
            # Try openpyxl for xlsx
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data))
            content.metadata["sheets"] = wb.sheetnames

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                sheet_data = []
                for row in ws.iter_rows(values_only=True):
                    sheet_data.append([str(cell) if cell is not None else "" for cell in row])
                content.tables.append(sheet_data)

            # Combine all text
            all_text = []
            for table in content.tables:
                for row in table:
                    all_text.extend(row)
            content.text = " | ".join(all_text)

        except ImportError:
            # Fallback to csv
            try:
                text_data = data.decode('utf-8', errors='ignore')
                reader = csv.reader(io.StringIO(text_data))
                table = list(reader)
                content.tables.append(table)
                content.text = "\n".join([",".join(row) for row in table])
            except Exception as e:
                errors.append(f"Spreadsheet parsing error: {str(e)}")
        except Exception as e:
            errors.append(f"Spreadsheet parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        content.metadata["_warnings"] = warnings
        return content

    def _parse_text(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []

        try:
            content.text = data.decode('utf-8', errors='ignore')
            content.metadata["lines"] = content.text.count('\n') + 1
            content.metadata["chars"] = len(content.text)
        except Exception as e:
            errors.append(f"Text parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        return content

    def _parse_html(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []

        try:
            from bs4 import BeautifulSoup
            html_text = data.decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_text, 'html.parser')

            content.text = soup.get_text(separator='\n', strip=True)
            content.metadata["title"] = soup.title.string if soup.title else ""

            # Extract tables
            for table in soup.find_all('table'):
                table_data = []
                for row in table.find_all('tr'):
                    row_data = []
                    for cell in row.find_all(['td', 'th']):
                        row_data.append(cell.get_text(strip=True))
                    table_data.append(row_data)
                if table_data:
                    content.tables.append(table_data)

            # Extract images
            for img in soup.find_all('img'):
                content.images.append({
                    "src": img.get('src', ''),
                    "alt": img.get('alt', ''),
                    "width": img.get('width'),
                    "height": img.get('height')
                })

        except ImportError:
            errors.append("BeautifulSoup4 not installed")
        except Exception as e:
            errors.append(f"HTML parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        return content

    def _parse_word(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []

        try:
            import docx
            doc = docx.Document(io.BytesIO(data))

            texts = []
            for para in doc.paragraphs:
                texts.append(para.text)

            content.text = "\n".join(texts)

            # Extract tables
            for table in doc.tables:
                table_data = []
                for row in table.rows:
                    row_data = [cell.text for cell in row.cells]
                    table_data.append(row_data)
                content.tables.append(table_data)

        except ImportError:
            errors.append("python-docx not installed")
        except Exception as e:
            errors.append(f"Word parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        return content

    def _parse_powerpoint(self, data: bytes) -> ExtractedContent:
        content = ExtractedContent()
        errors = []

        try:
            from pptx import Presentation
            prs = Presentation(io.BytesIO(data))

            texts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            texts.append(para.text)

            content.text = "\n".join(texts)
            content.metadata["slides"] = len(prs.slides)

        except ImportError:
            errors.append("python-pptx not installed")
        except Exception as e:
            errors.append(f"PowerPoint parsing error: {str(e)}")

        content.metadata["_errors"] = errors
        return content

    def register_parser(self, doc_type: DocumentType, parser: Callable[[bytes], ExtractedContent]):
        with self._lock:
            self._parsers[doc_type] = parser

    def get_supported_types(self) -> list[DocumentType]:
        return list(self._parsers.keys())


_document_extractor: DocumentExtractor | None = None


def get_document_extractor() -> DocumentExtractor:
    global _document_extractor
    if _document_extractor is None:
        _document_extractor = DocumentExtractor()
    return _document_extractor


import time
