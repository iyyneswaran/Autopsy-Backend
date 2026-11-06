"""Fast synthetic regression tests for the safety contracts of all eight layers.

Run from ai with PYTHONPATH=. These tests do not connect to a database.
"""
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql://unused@localhost/unused_test')
from app.pipeline.ingestion.checksum import compute_checksums_from_stream
from app.services.document_reader import read_document
from app.pipeline.ingestion.ocr.pipeline import OCRPipeline
from app.pipeline.ingestion.ocr.schemas import OCRPipelineConfig, ContentType
from app.pipeline.extraction.nlp.regex_extractor import RegexExtractor
from app.pipeline.structuring.schemas import StructuredEntity, ForensicEntityGraph, EntityType
from app.pipeline.structuring.value_normalizer import ValueNormalizer
from app.pipeline.normalization.stages.toxicology_normalizer import _classify_level
from app.pipeline.correlation.entity_matcher import EntityMatcher
from app.pipeline.temporal.temporal_parser import TemporalParser
from app.pipeline.temporal.timeline_builder import TimelineBuilder
from app.pipeline.tod_estimation.tod_parser import TODParser
from app.pipeline.anomaly_detection.contradiction_rules import ContradictionRules


def graph(kind, value, assertion='EXTRACTED_ASSERTION'):
    entity=StructuredEntity(entity_type=EntityType(kind),raw_value=value,canonical_value=value,
        confidence=.8,metadata={'assertion_status':assertion})
    return ForensicEntityGraph(entities={kind:[entity]})


class EngineContracts(unittest.TestCase):
    def test_acquisition_stream_integrity(self):
        content=b'SYNTHETIC\x00original\r\nbytes'
        result=compute_checksums_from_stream(io.BytesIO(content),chunk_size=3)
        self.assertEqual(result.sha256,hashlib.sha256(content).hexdigest())
        self.assertEqual(result.size_bytes,len(content))

    def test_ocr_reads_full_native_document(self):
        content=('Synthetic source line\n'*500)+'Final observation: preserved'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.txt';path.write_text(content,encoding='utf-8')
            result=read_document(str(path),'synthetic','text/plain')
        self.assertEqual(result.pages[0].text,content)
        self.assertEqual(result.pages[0].page_number,0)

    def test_ocr_engine_failure_is_explicit(self):
        with patch('app.pipeline.ingestion.ocr.tesseract_engine.extract_text',side_effect=RuntimeError('synthetic missing executable')):
            with self.assertRaisesRegex(RuntimeError,'Local OCR failed'):
                OCRPipeline()._run_tesseract_ocr(None,OCRPipelineConfig(),ContentType.PRINTED)

    def test_extraction_measurements_retain_units_and_offsets(self):
        source='Ethanol: 20 mg/dL\nMorphine: 4 ng/mL\nInjury 1: No fracture of skull.'
        spans=RegexExtractor().extract(source)
        values={s.source_span.raw_text for s in spans}
        self.assertIn('Ethanol: 20 mg/dL',values)
        self.assertIn('Morphine: 4 ng/mL',values)
        for span in spans:
            self.assertEqual(source[span.source_span.start_char:span.source_span.end_char],span.source_span.raw_text)

    def test_structuring_preserves_original_and_records_normalization(self):
        entity=StructuredEntity(entity_type=EntityType.INJURY,raw_value='Bruise on left forearm',canonical_value='Bruise on left forearm')
        normalized=ValueNormalizer().normalize_entities([entity])[0]
        self.assertEqual(normalized.raw_value,'Bruise on left forearm')
        self.assertEqual(normalized.canonical_value,'contusion on left forearm')
        self.assertTrue(normalized.provenance.transformations)

    def test_normalization_has_no_universal_toxicity_cutoff(self):
        for value in (0,20,600):
            self.assertEqual(_classify_level('ethanol',value),'UNINTERPRETED_REQUIRES_LAB_CONTEXT')

    def test_correlation_does_not_match_distinct_absent_injuries(self):
        graphs=[('a',graph('INJURY','No fracture of skull documented.','NEGATED')),
            ('b',graph('INJURY','No ligature mark documented.','NEGATED'))]
        self.assertEqual(EntityMatcher().match_entities(graphs),[])

    def test_temporal_never_invents_a_timezone_or_valid_date(self):
        parser=TemporalParser()
        for value in ('2026-02-30T25:70:00+05:30','2026-10-01T03:15:00','Around 2026-10-01T03:15:00+05:30'):
            self.assertIsNone(parser.parse_text(value)[0].time_window.earliest)
        self.assertEqual(parser.parse_text('2026-10-01T03:15:00+05:30')[0].time_window.earliest,'2026-10-01T03:15:00+05:30')

    def test_tod_does_not_turn_negation_into_a_signal(self):
        self.assertEqual(TODParser().extract_signals([('a',graph('TIME_OF_DEATH','No PMI established','NEGATED'))]),[])

    def test_timeline_respects_event_category_without_inventing_registration(self):
        data=graph('SCENE_REFERENCE','2026-10-01T03:15:00+05:30')
        data.entities['SCENE_REFERENCE'][0].metadata['event_category']='LAST_SEEN_ALIVE'
        events=TimelineBuilder().build_events([('a',data),('b',graph('CASE_IDENTIFIER','SYN-104/2026'))])
        self.assertEqual(len(events),1)
        self.assertTrue(events[0].label.startswith('Last Seen Alive:'))

    def test_anomalies_do_not_equate_lexical_difference_with_conflict(self):
        findings=ContradictionRules().detect([('a',graph('CAUSE_OF_DEATH','Pending histology and toxicology')),
            ('b',graph('CAUSE_OF_DEATH','No cause established'))])
        self.assertEqual(findings,[])


if __name__ == '__main__':
    unittest.main(verbosity=2)
