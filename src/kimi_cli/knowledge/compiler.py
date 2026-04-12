from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from .models import DocumentMetadata

def compile_wiki_index(root: Path):
    """
    Scans knowledge/ and raw/ for all documents and generates a high-level index.md.
    """
    documents: List[DocumentMetadata] = []
    
    # Scan for metadata.json files in raw/ and knowledge/
    for folder in ["raw", "knowledge"]:
        folder_path = root / folder
        if not folder_path.exists():
            continue
            
        for metadata_path in folder_path.rglob("metadata.json"):
            try:
                with open(metadata_path, "r") as f:
                    metadata = DocumentMetadata.model_validate_json(f.read())
                documents.append(metadata)
            except Exception:
                # Skip invalid metadata
                continue

    index_path = root / "index.md"
    
    if not documents:
        with open(index_path, "w") as f:
            f.write("# Knowledge Base Index\n\nNo documents found.\n")
        return

    # Sort documents by created_at (most recent first) for Recently Added
    sorted_by_date = sorted(documents, key=lambda x: x.created_at, reverse=True)
    recently_added = sorted_by_date[:5]

    # Group documents by category and subcategory
    # category -> subcategory -> List[DocumentMetadata]
    grouped: Dict[str, Dict[str, List[DocumentMetadata]]] = defaultdict(lambda: defaultdict(list))
    for doc in documents:
        grouped[doc.category.value][doc.subcategory].append(doc)

    lines = ["# Knowledge Base Index\n"]
    
    # Recently Added Section
    lines.append("## Recently Added")
    for doc in recently_added:
        short_id = str(doc.id)[:8]
        tags_str = ", ".join(doc.tags)
        lines.append(f"- [{short_id}] **{doc.title}**: {doc.description} (Tags: {tags_str})")
    lines.append("")

    # Main Body: Organized by Category and Subcategory
    # Sort categories alphabetically
    for category in sorted(grouped.keys()):
        lines.append(f"## {category}")
        
        # Sort subcategories alphabetically
        subcategories = grouped[category]
        for subcategory in sorted(subcategories.keys()):
            lines.append(f"### {subcategory}")
            
            # Sort documents in subcategory by title
            docs_in_sub = sorted(subcategories[subcategory], key=lambda x: x.title)
            for doc in docs_in_sub:
                short_id = str(doc.id)[:8]
                tags_str = ", ".join(doc.tags)
                lines.append(f"- [{short_id}] **{doc.title}**: {doc.description} (Tags: {tags_str})")
            lines.append("")

    with open(index_path, "w") as f:
        f.write("\n".join(lines))
