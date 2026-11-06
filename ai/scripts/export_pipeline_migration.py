"""Generate reviewable additive DDL only for AI-owned tables. Never apply it here."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_mock_engine
from app.core.database import Base
import app.models

shared = {'users', 'investigations', 'evidence', 'audit_logs', 'analysis', 'analyses'}
statements = []
engine = create_mock_engine('postgresql://', lambda sql, *args, **kwargs: statements.append(str(sql.compile(dialect=engine.dialect)).strip() + ';'))
tables = [table for table in Base.metadata.sorted_tables if table.name not in shared]
Base.metadata.create_all(engine, tables=tables, checkfirst=False)
destination = Path(__file__).resolve().parents[2] / 'server/prisma/migrations/202611030002_case_pipeline/migration.sql'
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text('-- AI-owned schema generated from SQLAlchemy. Shared tables are Prisma-owned.\n\n' + '\n\n'.join(statements), encoding='utf-8')
print(f'Wrote additive DDL for {len(tables)} AI-owned tables')
