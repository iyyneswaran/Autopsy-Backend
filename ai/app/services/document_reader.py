"""Read original evidence into the existing OCR contract; never use metadata previews."""
from pathlib import Path
from app.pipeline.ingestion.ocr.schemas import DocumentOCRResult, PageOCRResult, OCREngine, OCRPipelineConfig
from app.pipeline.ingestion.ocr.pipeline import OCRPipeline


def read_document(path: str, evidence_id: str, mime: str) -> DocumentOCRResult:
    pages = []
    if mime in ('text/plain', 'text/csv', 'application/json'):
        content = Path(path).read_text(encoding='utf-8-sig')
        pages = [PageOCRResult(page_number=0, text=content, confidence=1, engine=OCREngine.NATIVE)]
    elif mime == 'application/pdf':
        import fitz
        with fitz.open(path) as doc:
            if len(doc) > 200:
                raise ValueError('Document exceeds the 200-page processing limit; no pages were silently omitted')
            # Mixed/scanned documents use the existing local OCR pipeline for all pages.
            texts = [page.get_text() for page in doc]
        if texts and all(text.strip() for text in texts):
            pages = [PageOCRResult(page_number=i, text=t, confidence=1, engine=OCREngine.NATIVE) for i, t in enumerate(texts)]
    elif not mime.startswith('image/'):
        raise ValueError(f'Extraction is not supported for {mime}; original evidence is preserved')
    if pages:
        result = DocumentOCRResult(document_id=evidence_id, pages=pages, page_count=len(pages),
            full_text='\n\n'.join(p.text for p in pages), overall_confidence=1, engines_used=['native'])
    else:
        result = OCRPipeline(OCRPipelineConfig(use_gemini_for_handwriting=False)).process_document(path, evidence_id)
        # The legacy OCR runner numbers pages from one; the extraction contract
        # uses zero-based page indexes consistently for native text and OCR.
        for index, page in enumerate(result.pages):
            page.page_number = index
            if not page.text.strip():
                result.warnings.append(f'Page {index + 1} has no recognized text; inspect the original page')
    if not result.full_text.strip() or any(s.status == 'failed' for s in result.pipeline_stages):
        raise ValueError('Text/OCR extraction failed: ' + '; '.join(result.warnings + [s.error or s.detail for s in result.pipeline_stages if s.status == 'failed']))
    return result
