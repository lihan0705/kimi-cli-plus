import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

import yaml

from . import paths
from . import graph
from .models import Category, DocumentMetadata, DocumentStatus, SearchResult


class KBStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # Main documents table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    slug TEXT DEFAULT '',
                    description TEXT,
                    tags TEXT,
                    category TEXT NOT NULL,
                    subcategory TEXT,
                    status TEXT NOT NULL,
                    confidence REAL,
                    relevance_score INTEGER,
                    temporal_type TEXT,
                    key_claims TEXT,
                    source_type TEXT,
                    original_source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Migration: Add slug column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = [row[1] for row in cursor.fetchall()]
            if "slug" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN slug TEXT DEFAULT ''")

            # FTS5 virtual table for content
            # We store the ID unindexed to join back to documents
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
                    id UNINDEXED,
                    content
                )
            """)

            # Links table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    link_type TEXT,
                    PRIMARY KEY (source_id, target_id, link_type),
                    FOREIGN KEY (source_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES documents(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def upsert_document(self, metadata: DocumentMetadata, content: str):
        data = metadata.model_dump()
        # Serialize fields that are not native SQLite types
        data["id"] = str(data["id"])
        data["tags"] = json.dumps(data["tags"])
        data["key_claims"] = json.dumps(data["key_claims"])
        data["created_at"] = data["created_at"].isoformat()
        data["updated_at"] = data["updated_at"].isoformat()

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        updates = ", ".join([f"{k} = excluded.{k}" for k in data.keys() if k != "id"])

        with self._get_connection() as conn:
            # Upsert document metadata
            conn.execute(f"""
                INSERT INTO documents ({columns})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {updates}
            """, list(data.values()))

            # Upsert content into FTS
            # Delete old entry first because FTS doesn't have ON CONFLICT
            conn.execute("DELETE FROM content_fts WHERE id = ?", (data["id"],))
            conn.execute("INSERT INTO content_fts (id, content) VALUES (?, ?)", (data["id"], content))
            conn.commit()

        # Update graph links
        self.update_document_links(metadata.id, content)

    def update_document_links(self, doc_id: UUID, content: str):
        """Extract and persist links from document content."""
        doc_id_str = str(doc_id)
        links = graph.extract_links(content)
        
        resolved_targets = []
        for link_text in links:
            target_id = graph.resolve_link(self, link_text)
            if target_id:
                resolved_targets.append(str(target_id))
        
        with self._get_connection() as conn:
            # Delete existing links where this document is the source
            conn.execute("DELETE FROM links WHERE source_id = ?", (doc_id_str,))
            
            # Insert new links
            for target_id_str in resolved_targets:
                conn.execute(
                    "INSERT OR IGNORE INTO links (source_id, target_id, link_type) VALUES (?, ?, ?)",
                    (doc_id_str, target_id_str, "wiki")
                )
            conn.commit()

    def get_backlinks(self, doc_id: UUID) -> List[DocumentMetadata]:
        """Get metadata of documents that link to the given document."""
        doc_id_str = str(doc_id)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT d.*
                FROM documents d
                JOIN links l ON d.id = l.source_id
                WHERE l.target_id = ?
                ORDER BY d.updated_at DESC
            """, (doc_id_str,))
            return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def get_outgoing_links(self, doc_id: UUID) -> List[DocumentMetadata]:
        """Get metadata of documents that this document links to."""
        doc_id_str = str(doc_id)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT d.*
                FROM documents d
                JOIN links l ON d.id = l.target_id
                WHERE l.source_id = ?
                ORDER BY d.updated_at DESC
            """, (doc_id_str,))
            return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def get_related_documents(self, doc_id: UUID, limit: int = 10) -> List[Tuple[DocumentMetadata, int]]:
        """
        Find related documents based on:
        - Links (inbound/outbound)
        - Shared tags (at least 2)
        Returns a list of (metadata, score) tuples.
        """
        doc_id_str = str(doc_id)
        
        # 1. Get target doc to extract tags
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id_str,))
            row = cursor.fetchone()
            if not row:
                return []
            target = self._row_to_metadata(row)
        
        target_tags = set(target.tags)
        
        # 2. Get all other documents and calculate scores
        related_results = []
        with self._get_connection() as conn:
            # Get linked doc IDs first for high weighting
            cursor = conn.execute("""
                SELECT source_id as linked_id FROM links WHERE target_id = ?
                UNION
                SELECT target_id as linked_id FROM links WHERE source_id = ?
            """, (doc_id_str, doc_id_str))
            linked_ids = {row["linked_id"] for row in cursor.fetchall()}
            
            # Fetch all documents except the current one
            cursor = conn.execute("SELECT * FROM documents WHERE id != ?", (doc_id_str,))
            for row in cursor.fetchall():
                other = self._row_to_metadata(row)
                score = 0
                is_linked = str(other.id) in linked_ids
                
                # Shared tags
                other_tags = set(other.tags)
                shared_tags = target_tags.intersection(other_tags)
                
                # Filter criteria: linked OR at least 2 shared tags
                if is_linked or len(shared_tags) >= 2:
                    if is_linked:
                        score += 10
                    score += len(shared_tags) * 2
                    related_results.append((other, score))
                    
        # Sort by score descending
        related_results.sort(key=lambda x: x[1], reverse=True)
        return related_results[:limit]

    def delete_document(self, doc_id: UUID):
        doc_id_str = str(doc_id)
        with self._get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id_str,))
            conn.execute("DELETE FROM content_fts WHERE id = ?", (doc_id_str,))
            conn.execute("DELETE FROM links WHERE source_id = ? OR target_id = ?", (doc_id_str, doc_id_str))
            conn.commit()

    def _row_to_metadata(self, row: sqlite3.Row) -> DocumentMetadata:
        data = dict(row)
        data["tags"] = json.loads(data["tags"])
        data["key_claims"] = json.loads(data["key_claims"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return DocumentMetadata.model_validate(data)

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT d.*, snippet(content_fts, 1, '...', '...', '...', 64) as snippet
                FROM documents d
                JOIN content_fts f ON d.id = f.id
                WHERE f.content MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit))
            return [
                SearchResult(
                    metadata=self._row_to_metadata(row),
                    snippet=row["snippet"]
                )
                for row in cursor.fetchall()
            ]

    def get_document(self, doc_id: UUID) -> Optional[Tuple[DocumentMetadata, str]]:
        doc_id_str = str(doc_id)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT d.*, f.content
                FROM documents d
                JOIN content_fts f ON d.id = f.id
                WHERE d.id = ?
            """, (doc_id_str,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_metadata(row), row["content"]

    def list_documents(
        self, category: Optional[Category] = None, status: Optional[DocumentStatus] = None
    ) -> List[DocumentMetadata]:
        query = "SELECT * FROM documents"
        params = []
        where_clauses = []

        if category:
            where_clauses.append("category = ?")
            params.append(category.value)
        if status:
            where_clauses.append("status = ?")
            params.append(status.value)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY updated_at DESC"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def sync_from_disk(self, root: Path):
        """
        Synchronize the database with the content on disk.
        Scans 'raw/' and 'knowledge/' directories for document structures.
        A valid document directory must contain both 'metadata.json' and 'document.md'.
        """
        found_ids = set()

        # Scan for metadata.json files
        for metadata_path in root.rglob("metadata.json"):
            doc_dir = metadata_path.parent
            content_path = doc_dir / "document.md"

            if not content_path.exists():
                continue

            try:
                # Load metadata
                with open(metadata_path, "r") as f:
                    metadata = DocumentMetadata.model_validate_json(f.read())
                
                # If slug is missing, recover from folder name
                if not metadata.slug:
                    metadata.slug = doc_dir.name

                # Read content
                with open(content_path, "r") as f:
                    content = f.read()

                # Upsert into database
                self.upsert_document(metadata, content)
                found_ids.add(str(metadata.id))
            except Exception as e:
                from loguru import logger
                logger.error(f"Error syncing document at {doc_dir}: {e}")

        # Cleanup: Remove documents from DB that were not found on disk
        with self._get_connection() as conn:
            # Get all current IDs in DB
            cursor = conn.execute("SELECT id FROM documents")
            db_ids = {row["id"] for row in cursor.fetchall()}

            ids_to_remove = db_ids - found_ids
            for doc_id in ids_to_remove:
                self.delete_document(UUID(doc_id))

    def _parse_yaml_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from a string."""
        if not content.startswith("---"):
            return {}

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}

    def sync_metadata_from_md(self, doc_dir: Path) -> Path:
        """
        Synchronize metadata from YAML frontmatter in document.md with metadata.json.
        Updates the SQLite database. Handles directory moves if category/subcategory changes.
        """
        content_path = doc_dir / "document.md"
        metadata_path = doc_dir / "metadata.json"

        if not content_path.exists() or not metadata_path.exists():
            return doc_dir

        # Read content and parse YAML
        with open(content_path, "r") as f:
            content = f.read()

        yaml_data = self._parse_yaml_frontmatter(content)

        # Load current metadata
        with open(metadata_path, "r") as f:
            metadata = DocumentMetadata.model_validate_json(f.read())

        if not yaml_data:
            # Idempotent: still sync to DB
            self.upsert_document(metadata, content)
            return doc_dir

        # Update fields from YAML
        # title, category, subcategory, tags, relevance_score, key_claims
        old_category = metadata.category
        old_subcategory = metadata.subcategory

        if "title" in yaml_data:
            metadata.title = yaml_data["title"]
        if "category" in yaml_data:
            metadata.category = Category(yaml_data["category"])
        if "subcategory" in yaml_data:
            metadata.subcategory = yaml_data["subcategory"]
        if "tags" in yaml_data:
            metadata.tags = yaml_data["tags"]
        if "relevance_score" in yaml_data:
            metadata.relevance_score = yaml_data["relevance_score"]
        if "key_claims" in yaml_data:
            metadata.key_claims = yaml_data["key_claims"]

        # Auto-promotion: if user edited YAML, it's no longer 'raw' or 'needs_review'
        if metadata.status in [DocumentStatus.raw, DocumentStatus.needs_review]:
            metadata.status = DocumentStatus.reviewed

        metadata.updated_at = datetime.now()

        # Handle Category/Subcategory Change
        target_dir = doc_dir
        if metadata.category != old_category or metadata.subcategory != old_subcategory:
            # Find KB root from doc_dir structure
            kb_root = None
            parts = doc_dir.parts
            if "knowledge" in parts:
                idx = parts.index("knowledge")
                kb_root = Path(*parts[:idx])
            elif "raw" in parts:
                idx = parts.index("raw")
                kb_root = Path(*parts[:idx])

            if kb_root:
                slug = paths.generate_slug(metadata.title, metadata.id)
                metadata.slug = slug
                target_dir = paths.get_document_dir(
                    kb_root, slug, metadata.status, metadata.category, metadata.subcategory
                )

                if target_dir != doc_dir:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(doc_dir), str(target_dir))
                    metadata_path = target_dir / "metadata.json"

        # Update metadata.json in the (possibly new) location
        with open(metadata_path, "w") as f:
            f.write(metadata.model_dump_json())

        # Update SQLite database
        self.upsert_document(metadata, content)

        return target_dir
