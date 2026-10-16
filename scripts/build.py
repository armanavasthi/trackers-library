#!/usr/bin/env python3
"""Deterministic static catalog compiler and artifact packager for Trackers Community Library.

Builds:
- dist/catalog-v1.json (Full compiled index with content counts & plan summaries)
- dist/categories.json
- dist/schemas/
- dist/artifacts/<id>/<version>/template.json
- dist/artifacts/<id>/<version>/<cover_image>
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Import validator logic from validate.py
from validate import (
    ValidationError,
    validate_all,
    validate_categories_file,
    validate_entry_package,
)


def compute_content_counts(template: Dict[str, Any]) -> Tuple[Dict[str, int], Optional[Dict[str, int]]]:
    """Compute normalized content counts and optional plan summary from a validated template."""
    kind = template.get("kind")
    content = template.get("content", {})

    sections_count = 0
    containers_count = 0
    leaves_count = 0
    resources_count = 0

    if kind == "study-template":
        study_sections = content.get("sections", [])
        sections_count = len(study_sections)
        for s in study_sections:
            topics = s.get("topics", [])
            containers_count += len(topics)
            for t in topics:
                subtopics = t.get("subtopics", [])
                leaves_count += len(subtopics)
                for sub in subtopics:
                    resources_count += len(sub.get("resources", []))

    elif kind == "dsa-template":
        dsa_sections = content.get("sections", [])
        sections_count = len(dsa_sections)
        for s in dsa_sections:
            patterns = s.get("patterns", [])
            containers_count += len(patterns)
            for p in patterns:
                problems = p.get("problems", [])
                leaves_count += len(problems)
                for prob in problems:
                    resources_count += len(prob.get("resources", []))

    elif kind == "workspace-template":
        study_sections = (content.get("study") or {}).get("sections", [])
        sections_count += len(study_sections)
        for s in study_sections:
            topics = s.get("topics", [])
            containers_count += len(topics)
            for t in topics:
                subtopics = t.get("subtopics", [])
                leaves_count += len(subtopics)
                for sub in subtopics:
                    resources_count += len(sub.get("resources", []))

        dsa_sections = (content.get("dsa") or {}).get("sections", [])
        sections_count += len(dsa_sections)
        for s in dsa_sections:
            patterns = s.get("patterns", [])
            containers_count += len(patterns)
            for p in patterns:
                problems = p.get("problems", [])
                leaves_count += len(problems)
                for prob in problems:
                    resources_count += len(prob.get("resources", []))

    counts = {
        "sections": sections_count,
        "containers": containers_count,
        "leaves": leaves_count,
        "resources": resources_count,
    }

    plan = content.get("plan")
    plan_summary: Optional[Dict[str, int]] = None
    if plan and isinstance(plan, dict):
        entries = plan.get("entries", [])
        if entries:
            duration_days = max((e.get("dayOffset", 0) for e in entries), default=0) + 1
            estimated_minutes = sum(
                e.get("estimatedMinutes", 0)
                for e in entries
                if isinstance(e.get("estimatedMinutes"), int)
            )
            plan_summary = {
                "totalEntries": len(entries),
                "durationDays": duration_days,
                "estimatedMinutes": estimated_minutes,
            }

    return counts, plan_summary


def get_git_revision(repo_root: Path) -> str:
    """Get current git commit hash or default fallback."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "dev-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")


def build_catalog(repo_root: Path, dist_dir: Path, schema_base_url: str = "https://trackers.example") -> None:
    print(f"📦 Building Trackers Library Distribution...")
    print(f"   Source root: {repo_root}")
    print(f"   Output dir:  {dist_dir}")

    # 1. Run full validation
    validated_packages = validate_all(repo_root)

    # 2. Prepare output directory
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy categories.json and schemas
    cat_src = repo_root / "categories.json"
    cat_data = json.loads(cat_src.read_text(encoding="utf-8"))
    shutil.copy2(cat_src, dist_dir / "categories.json")

    schemas_src = repo_root / "schemas"
    if schemas_src.exists():
        shutil.copytree(schemas_src, dist_dir / "schemas")

    # 4. Process entries & artifacts
    published_entries: List[Dict[str, Any]] = []

    for pkg in validated_packages:
        entry = pkg["entry"]
        template = pkg["template"]
        entry_dir = pkg["entry_dir"]
        cover_file = pkg.get("cover_file")

        entry_id = entry["id"]
        version = entry["version"]

        # Target artifact dir: dist/artifacts/<id>/<version>/
        target_art_dir = dist_dir / "artifacts" / entry_id / version
        target_art_dir.mkdir(parents=True, exist_ok=True)

        # Copy template.json
        shutil.copy2(entry_dir / "template.json", target_art_dir / "template.json")
        rel_template_path = entry["template"]["path"]

        # Copy cover if present
        published_cover = None
        if cover_file and cover_file.exists():
            shutil.copy2(cover_file, target_art_dir / cover_file.name)
            cov_meta = entry["cover"]
            published_cover = {
                "path": cov_meta["path"],
                "alt": cov_meta["alt"],
                "sha256": cov_meta["sha256"],
                "bytes": cov_meta["bytes"],
                "width": cov_meta["width"],
                "height": cov_meta["height"],
            }

        counts, plan_summary = compute_content_counts(template)

        published_entry: Dict[str, Any] = {
            "id": entry["id"],
            "slug": entry["slug"],
            "version": entry["version"],
            "packageType": entry["packageType"],
            "templateKind": entry["templateKind"],
            "title": entry["title"],
            "summary": entry["summary"],
            "description": entry["description"],
            "categoryIds": entry["categoryIds"],
            "tags": entry["tags"],
            "levels": entry["levels"],
            "estimatedWeeks": entry["estimatedWeeks"],
            "creator": entry["creator"],
            "license": entry["license"],
            "contentCounts": counts,
            "template": {
                "path": rel_template_path,
                "sha256": entry["template"]["sha256"],
                "bytes": entry["template"]["bytes"],
            },
            "publishedAt": entry["publishedAt"],
            "updatedAt": entry["updatedAt"],
        }

        if plan_summary is not None:
            published_entry["planSummary"] = plan_summary
        if published_cover is not None:
            published_entry["cover"] = published_cover

        published_entries.append(published_entry)

    # Sort entries deterministically by ID
    published_entries.sort(key=lambda x: x["id"])

    # 5. Build catalog-v1.json
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    revision = get_git_revision(repo_root)

    catalog_doc: Dict[str, Any] = {
        "$schema": f"{schema_base_url}/schemas/learning-library-catalog-v1.json",
        "schemaVersion": 1,
        "revision": revision,
        "generatedAt": now_utc,
        "categories": sorted(cat_data, key=lambda c: c.get("displayOrder", 999)),
        "featuredEntryIds": [e["id"] for e in published_entries if "interview-preparation" in e.get("categoryIds", [])][:5],
        "entries": published_entries,
    }

    catalog_file = dist_dir / "catalog-v1.json"
    catalog_file.write_text(json.dumps(catalog_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n✨ Successfully compiled {len(published_entries)} catalog entries to {catalog_file}!")


def main():
    parser = argparse.ArgumentParser(description="Build Trackers Community Library catalog and artifacts.")
    parser.add_argument("--repo-root", default=".", help="Path to repository root")
    parser.add_argument("--dist-dir", default="./dist", help="Target distribution directory")
    parser.add_argument("--schema-base-url", default="https://trackers.example", help="Base URL for $schema definition")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    dist_dir = Path(args.dist_dir).resolve()

    try:
        build_catalog(repo_root, dist_dir, schema_base_url=args.schema_base_url)
        sys.exit(0)
    except Exception as exc:
        print(f"\n❌ BUILD ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
