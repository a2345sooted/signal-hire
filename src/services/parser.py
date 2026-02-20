import io
import logging
from typing import Optional
import pypdf
from docx import Document

logger = logging.getLogger(__name__)

async def extract_text_from_bytes(file_data: bytes, filename: str) -> Optional[str]:
    """
    Extracts text from PDF or DOCX file bytes.
    """
    extension = filename.split(".")[-1].lower()
    
    try:
        if extension == "pdf":
            return extract_text_from_pdf(file_data)
        elif extension in ["docx", "doc"]:
            return extract_text_from_docx(file_data)
        else:
            logger.warning(f"Unsupported file extension: {extension}")
            return None
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {str(e)}")
        return None

def extract_text_from_pdf(file_data: bytes) -> str:
    text = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_data))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        logger.error(f"PyPDF extraction failed: {str(e)}")
        raise
    return text.strip()

def extract_text_from_docx(file_data: bytes) -> str:
    text = ""
    try:
        doc = Document(io.BytesIO(file_data))
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"
    except Exception as e:
        logger.error(f"python-docx extraction failed: {str(e)}")
        raise
    return text.strip()
