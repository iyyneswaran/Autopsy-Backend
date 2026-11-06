-- AI-owned schema generated from SQLAlchemy. Shared tables are Prisma-owned.

CREATE TYPE file_category_enum AS ENUM ('DOCUMENT', 'IMAGE', 'VIDEO', 'STRUCTURED');

CREATE TYPE ingestion_status_enum AS ENUM ('PENDING', 'UPLOADING', 'VALIDATING', 'EXTRACTING_METADATA', 'NORMALIZING', 'COMPLETED', 'FAILED', 'DUPLICATE');

CREATE TYPE normalization_status_enum AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'PARTIAL', 'FAILED');

CREATE TYPE extraction_status_enum AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'PARTIAL', 'FAILED');

CREATE TABLE acquisition_logs (
	id UUID NOT NULL, 
	evidence_file_id UUID, 
	upload_session_id UUID, 
	user_id UUID, 
	action VARCHAR(100) NOT NULL, 
	detail TEXT, 
	context JSON, 
	correlation_id VARCHAR(64), 
	ip_address VARCHAR(45), 
	user_agent VARCHAR(512), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_acq_log_evidence ON acquisition_logs (evidence_file_id);

CREATE INDEX ix_acq_log_action ON acquisition_logs (action);

CREATE INDEX ix_acq_log_created ON acquisition_logs (created_at);

CREATE TABLE correlation_records (
	id UUID NOT NULL, 
	case_id UUID, 
	status extraction_status_enum, 
	correlation_graph JSON, 
	schema_version VARCHAR(20), 
	evidence_file_ids JSON, 
	cluster_count INTEGER, 
	edge_count INTEGER, 
	contradiction_count INTEGER, 
	evidence_group_count INTEGER, 
	overall_confidence FLOAT, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_corr_case ON correlation_records (case_id);

CREATE INDEX ix_corr_created ON correlation_records (created_at);

CREATE INDEX ix_corr_status ON correlation_records (status);

CREATE TABLE upload_sessions (
	id UUID NOT NULL, 
	user_id UUID, 
	case_id UUID, 
	status ingestion_status_enum, 
	total_files INTEGER, 
	completed_files INTEGER, 
	failed_files INTEGER, 
	is_resumable BOOLEAN, 
	chunk_size INTEGER, 
	uploaded_chunks JSON, 
	session_metadata JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_upload_sessions_status ON upload_sessions (status);

CREATE INDEX ix_upload_sessions_user ON upload_sessions (user_id);

CREATE TABLE case_pipeline_runs (
	id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	requested_by UUID NOT NULL, 
	version INTEGER NOT NULL, 
	request_key VARCHAR(128) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	schema_version VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	evidence_ids JSON NOT NULL, 
	retry_of UUID, 
	warnings JSON, 
	error TEXT, 
	changes JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (case_id, version), 
	UNIQUE (case_id, request_key), 
	FOREIGN KEY(case_id) REFERENCES investigations (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(retry_of) REFERENCES case_pipeline_runs (id)
);

CREATE INDEX ix_case_pipeline_runs_case_id ON case_pipeline_runs (case_id);

CREATE INDEX ix_case_pipeline_runs_status ON case_pipeline_runs (status);

CREATE TABLE hypothesis_revisions (
	id UUID NOT NULL, 
	hypothesis_id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	description TEXT NOT NULL, 
	notes TEXT NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	assessments JSON NOT NULL, 
	user_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (hypothesis_id, version), 
	FOREIGN KEY(case_id) REFERENCES investigations (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_hypothesis_revisions_hypothesis_id ON hypothesis_revisions (hypothesis_id);

CREATE INDEX ix_hypothesis_revisions_case_id ON hypothesis_revisions (case_id);

CREATE TABLE evidence_files (
	id UUID NOT NULL, 
	original_filename VARCHAR(512) NOT NULL, 
	mime_type VARCHAR(255) NOT NULL, 
	category file_category_enum NOT NULL, 
	storage_key VARCHAR(1024) NOT NULL, 
	storage_path VARCHAR(2048) NOT NULL, 
	file_size BIGINT NOT NULL, 
	sha256_hash VARCHAR(64) NOT NULL, 
	md5_hash VARCHAR(32), 
	version INTEGER NOT NULL, 
	parent_file_id UUID, 
	status ingestion_status_enum NOT NULL, 
	error_message TEXT, 
	case_id UUID, 
	uploaded_by UUID, 
	upload_session_id UUID, 
	tags JSON, 
	source_attribution VARCHAR(512), 
	provenance JSON, 
	is_deleted BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (storage_key), 
	FOREIGN KEY(upload_session_id) REFERENCES upload_sessions (id)
);

CREATE INDEX ix_evidence_files_created ON evidence_files (created_at);

CREATE INDEX ix_evidence_files_case ON evidence_files (case_id);

CREATE INDEX ix_evidence_files_sha256 ON evidence_files (sha256_hash);

CREATE INDEX ix_evidence_files_status ON evidence_files (status);

CREATE INDEX ix_evidence_files_category ON evidence_files (category);

CREATE TABLE temporal_records (
	id UUID NOT NULL, 
	case_id UUID, 
	correlation_id UUID, 
	status extraction_status_enum, 
	forensic_timeline JSON, 
	schema_version VARCHAR(20), 
	evidence_file_ids JSON, 
	event_count INTEGER, 
	relation_count INTEGER, 
	conflict_count INTEGER, 
	tod_candidate_count INTEGER, 
	overall_confidence FLOAT, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(correlation_id) REFERENCES correlation_records (id)
);

CREATE INDEX ix_temp_case ON temporal_records (case_id);

CREATE INDEX ix_temp_status ON temporal_records (status);

CREATE INDEX ix_temp_created ON temporal_records (created_at);

CREATE INDEX ix_temp_correlation ON temporal_records (correlation_id);

CREATE TABLE case_pipeline_stages (
	id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	scope VARCHAR(40) NOT NULL, 
	name VARCHAR(40) NOT NULL, 
	cache_key VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	schema_version VARCHAR(30), 
	input_version VARCHAR(30), 
	output JSON, 
	record_id UUID, 
	reused_from UUID, 
	warnings JSON, 
	error TEXT, 
	duration_ms FLOAT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (run_id, scope, name), 
	FOREIGN KEY(run_id) REFERENCES case_pipeline_runs (id), 
	FOREIGN KEY(reused_from) REFERENCES case_pipeline_stages (id)
);

CREATE INDEX ix_case_pipeline_stages_run_id ON case_pipeline_stages (run_id);

CREATE INDEX ix_stage_cache ON case_pipeline_stages (cache_key, status);

CREATE TABLE finding_reviews (
	id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	target_id VARCHAR(200) NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	note TEXT NOT NULL, 
	correction TEXT, 
	user_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES investigations (id), 
	FOREIGN KEY(run_id) REFERENCES case_pipeline_runs (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_finding_reviews_case_id ON finding_reviews (case_id);

CREATE INDEX ix_finding_reviews_target_id ON finding_reviews (target_id);

CREATE TABLE file_checksums (
	id UUID NOT NULL, 
	evidence_file_id UUID NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	md5 VARCHAR(32), 
	file_size BIGINT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evidence_file_id) REFERENCES evidence_files (id), 
	UNIQUE (sha256)
);

CREATE UNIQUE INDEX ix_checksum_sha256 ON file_checksums (sha256);

CREATE TABLE metadata_records (
	id UUID NOT NULL, 
	evidence_file_id UUID NOT NULL, 
	meta_type VARCHAR(50) NOT NULL, 
	extracted_data JSON NOT NULL, 
	extraction_version VARCHAR(20), 
	confidence FLOAT, 
	warnings JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evidence_file_id) REFERENCES evidence_files (id)
);

CREATE INDEX ix_meta_evidence ON metadata_records (evidence_file_id);

CREATE INDEX ix_meta_type ON metadata_records (meta_type);

CREATE TABLE normalization_records (
	id UUID NOT NULL, 
	evidence_file_id UUID NOT NULL, 
	status normalization_status_enum, 
	canonical_output JSON, 
	schema_version VARCHAR(20), 
	normalization_version INTEGER, 
	quality_score FLOAT, 
	completeness_score FLOAT, 
	confidence_score FLOAT, 
	quality_report JSON, 
	anomalies_detected JSON, 
	anomaly_count INTEGER, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evidence_file_id) REFERENCES evidence_files (id)
);

CREATE INDEX ix_norm_evidence ON normalization_records (evidence_file_id);

CREATE INDEX ix_norm_status ON normalization_records (status);

CREATE TABLE ocr_extraction_records (
	id UUID NOT NULL, 
	evidence_file_id UUID NOT NULL, 
	status extraction_status_enum, 
	extraction_envelope JSON, 
	schema_version VARCHAR(20), 
	page_count INTEGER, 
	total_spans INTEGER, 
	overall_confidence FLOAT, 
	extractors_used JSON, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evidence_file_id) REFERENCES evidence_files (id)
);

CREATE INDEX ix_ocr_extract_status ON ocr_extraction_records (status);

CREATE INDEX ix_ocr_extract_evidence ON ocr_extraction_records (evidence_file_id);

CREATE TABLE tod_estimation_records (
	id UUID NOT NULL, 
	case_id UUID, 
	temporal_id UUID, 
	status extraction_status_enum, 
	tod_estimation_result JSON, 
	schema_version VARCHAR(20), 
	evidence_file_ids JSON, 
	candidate_count INTEGER, 
	signal_count INTEGER, 
	conflict_count INTEGER, 
	overall_confidence FLOAT, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(temporal_id) REFERENCES temporal_records (id)
);

CREATE INDEX ix_tod_created ON tod_estimation_records (created_at);

CREATE INDEX ix_tod_temporal ON tod_estimation_records (temporal_id);

CREATE INDEX ix_tod_status ON tod_estimation_records (status);

CREATE INDEX ix_tod_case ON tod_estimation_records (case_id);

CREATE TABLE anomaly_detection_records (
	id UUID NOT NULL, 
	case_id UUID, 
	temporal_id UUID, 
	tod_estimation_id UUID, 
	status extraction_status_enum, 
	anomaly_report JSON, 
	schema_version VARCHAR(20), 
	evidence_file_ids JSON, 
	anomaly_count INTEGER, 
	contradiction_count INTEGER, 
	critical_count INTEGER, 
	high_count INTEGER, 
	overall_confidence FLOAT, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(temporal_id) REFERENCES temporal_records (id), 
	FOREIGN KEY(tod_estimation_id) REFERENCES tod_estimation_records (id)
);

CREATE INDEX ix_anomaly_status ON anomaly_detection_records (status);

CREATE INDEX ix_anomaly_case ON anomaly_detection_records (case_id);

CREATE INDEX ix_anomaly_created ON anomaly_detection_records (created_at);

CREATE INDEX ix_anomaly_tod ON anomaly_detection_records (tod_estimation_id);

CREATE TABLE forensic_entity_records (
	id UUID NOT NULL, 
	evidence_file_id UUID NOT NULL, 
	ocr_extraction_id UUID, 
	status extraction_status_enum, 
	entity_graph JSON, 
	schema_version VARCHAR(20), 
	entity_count INTEGER, 
	entity_types_found JSON, 
	overall_confidence FLOAT, 
	provenance_depth INTEGER, 
	validation_passed BOOLEAN, 
	stages_completed JSON, 
	stages_failed JSON, 
	error_message TEXT, 
	processing_time_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evidence_file_id) REFERENCES evidence_files (id), 
	FOREIGN KEY(ocr_extraction_id) REFERENCES ocr_extraction_records (id)
);

CREATE INDEX ix_forensic_ent_evidence ON forensic_entity_records (evidence_file_id);

CREATE INDEX ix_forensic_ent_extraction ON forensic_entity_records (ocr_extraction_id);

CREATE INDEX ix_forensic_ent_status ON forensic_entity_records (status);