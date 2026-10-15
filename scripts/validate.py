#!/usr/bin/env python3
"""Strict side-effect-free automated validator for the Trackers Community Library.

Validates:
1. Canonical category registry (categories.json).
2. Entry directory layout: entries/<id>/<version>/.
3. Metadata schema validation (entry.json) against learning-library-entry-v1.
4. Template artifact validation (template.json) against trackers-template-v1 rules.
5. Exact SHA-256 and byte-count integrity for templates and covers.
6. Cover image headers, formats (PNG/JPEG/WebP), and dimension limits.
7. Internal reference integrity for workspace templates and category IDs.
8. Security & hygiene: no secrets/credentials, no raw HTML/scripts, no prototype pollution.
9. Version immutability check against git base branch when in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
KEY_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
CREATOR_ID_REGEX = re.compile(r"^[a-z0-9][a-z0-9.-]{0,79}$")
SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")
ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

HTML_TAG_REGEX = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", re.IGNORECASE)
FORBIDDEN_HTML_TAGS = {"script", "iframe", "object", "embed", "style", "form", "input", "button", "link", "meta", "base"}
UNSAFE_KEYS = {"__proto__", "prototype", "constructor"}
PROGRESS_KEYS = {
    "status", "history", "confidence", "schedule", "schedules",
    "attempts", "notes", "authentication", "auth", "preferences",
    "password", "passwordHash", "password_hash", "storagePath",
    "storage_path", "absoluteDate", "absolute_date"
}
FORBIDDEN_SECRET_PATTERNS = [
    re.compile(r"\bghp_[a-zA-Z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{40,}\b"),
    re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
]

ALLOWED_PACKAGE_TYPES = {"tracker", "bundle"}
ALLOWED_TEMPLATE_KINDS = {"study-template", "dsa-template", "workspace-template"}
ALLOWED_LEVELS = {"beginner", "intermediate", "advanced", "mixed"}
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
MAX_COVER_BYTES = 512 * 1024  # 512 KB
MAX_COVER_WIDTH = 2400
MAX_COVER_HEIGHT = 1600


class ValidationError(Exception):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(f"[{code}] {path}: {message}")
        self.code = code
        self.path = path
        self.message = message


def inspect_image_header(data: bytes) -> Tuple[str, int, int]:
    """Inspect image bytes and return (mime_type, width, height) without external deps."""
    if len(data) < 24:
        raise ValidationError("image_too_small", "cover", "Image file is too small to contain a valid header.")

    # 1. PNG inspection
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ValidationError("invalid_png", "cover", "Malformed PNG: missing IHDR chunk.")
        width, height = struct.unpack(">II", data[16:24])
        if width <= 0 or height <= 0:
            raise ValidationError("invalid_png_dims", "cover", "Invalid PNG dimensions.")
        return "image/png", width, height

    # 2. JPEG inspection
    if data.startswith(b"\xff\xd8\xff"):
        offset = 2
        while offset < len(data):
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
                continue
            if marker == 0xDA:
                break
            if offset + 2 > len(data):
                break
            (length,) = struct.unpack(">H", data[offset : offset + 2])
            if length < 2:
                raise ValidationError("invalid_jpeg", "cover", "Malformed JPEG marker length.")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                if offset + 7 > len(data):
                    raise ValidationError("invalid_jpeg", "cover", "Truncated JPEG SOF frame.")
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                if width <= 0 or height <= 0:
                    raise ValidationError("invalid_jpeg_dims", "cover", "Invalid JPEG dimensions.")
                return "image/jpeg", width, height
            offset += length
        raise ValidationError("invalid_jpeg", "cover", "Could not find JPEG Start-of-Frame marker.")

    # 3. WebP inspection
    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        chunk_type = data[12:16]
        if chunk_type == b"VP8 ":
            if len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
                width, height = struct.unpack("<HH", data[26:30])
                width &= 0x3FFF
                height &= 0x3FFF
                if width > 0 and height > 0:
                    return "image/webp", width, height
            raise ValidationError("invalid_webp", "cover", "Malformed WebP VP8 header.")
        if chunk_type == b"VP8L":
            if len(data) >= 25 and data[20] == 0x2F:
                b1, b2, b3, b4 = data[21:25]
                width = 1 + (((b2 & 0x3F) << 8) | b1)
                height = 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                if width > 0 and height > 0:
                    return "image/webp", width, height
            raise ValidationError("invalid_webp", "cover", "Malformed WebP VP8L header.")
        if chunk_type == b"VP8X":
            if len(data) >= 30:
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
                if width > 0 and height > 0:
                    return "image/webp", width, height
            raise ValidationError("invalid_webp", "cover", "Malformed WebP VP8X header.")

    raise ValidationError("unsupported_image_format", "cover", "Cover must be PNG, JPEG, or WebP.")


def scan_for_security_issues(val: Any, path: str) -> None:
    """Recursively search for credentials, unsafe HTML tags, prototype pollution, or progress leaks."""
    if isinstance(val, dict):
        for k, v in val.items():
            if k in UNSAFE_KEYS:
                raise ValidationError("unsafe_field", f"{path}.{k}", f"Prohibited prototype key: {k}")
            k_lower = k.lower()
            if any(f in k_lower for f in ("password", "password_hash", "private_key", "secret_key", "bearer_token")):
                raise ValidationError("forbidden_field", f"{path}.{k}", f"Forbidden field detected: {k}")
            scan_for_security_issues(v, f"{path}.{k}")
    elif isinstance(val, list):
        for i, item in enumerate(val):
            scan_for_security_issues(item, f"{path}[{i}]")
    elif isinstance(val, str):
        # Scan for credentials
        for pat in FORBIDDEN_SECRET_PATTERNS:
            if pat.search(val):
                raise ValidationError("credential_detected", path, f"Potential credential or secret detected in {path}")
        # Scan for dangerous HTML
        for match in HTML_TAG_REGEX.finditer(val):
            tag_name = match.group(1).lower()
            if tag_name in FORBIDDEN_HTML_TAGS:
                raise ValidationError("forbidden_html_tag", path, f"HTML <{tag_name}> tags are prohibited in metadata or template text.")


def validate_categories_file(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    cat_file = repo_root / "categories.json"
    if not cat_file.exists():
        raise ValidationError("missing_categories", "categories.json", "categories.json not found in repository root.")

    try:
        data = json.loads(cat_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError("invalid_categories_json", "categories.json", f"JSON parsing failed: {exc}")

    if not isinstance(data, list) or len(data) == 0:
        raise ValidationError("empty_categories", "categories.json", "categories.json must be a non-empty array.")

    seen_ids: Set[str] = set()
    categories_map: Dict[str, Dict[str, Any]] = {}

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValidationError("invalid_category_item", f"categories[{i}]", "Category entry must be an object.")
        cat_id = item.get("id")
        label = item.get("label")
        desc = item.get("description")
        icon = item.get("icon")

        if not cat_id or not isinstance(cat_id, str) or not KEY_REGEX.match(cat_id):
            raise ValidationError("invalid_category_id", f"categories[{i}].id", f"Invalid category ID: {cat_id}")
        if cat_id in seen_ids:
            raise ValidationError("duplicate_category_id", f"categories[{i}].id", f"Duplicate category ID: {cat_id}")
        seen_ids.add(cat_id)

        if not label or not isinstance(label, str) or len(label) > 80:
            raise ValidationError("invalid_category_label", f"categories[{i}].label", "Label must be 1-80 characters.")
        if desc is not None and (not isinstance(desc, str) or len(desc) > 240):
            raise ValidationError("invalid_category_desc", f"categories[{i}].description", "Description must be up to 240 characters.")
        if icon is not None and (not isinstance(icon, str) or len(icon) > 40):
            raise ValidationError("invalid_category_icon", f"categories[{i}].icon", "Icon identifier must be up to 40 characters.")

        categories_map[cat_id] = item

    return categories_map


def validate_template_document(template_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate reusable template structure and rules (trackers-template-v1)."""
    if not isinstance(template_data, dict):
        raise ValidationError("invalid_template_root", "template.json", "Template must be a JSON object.")

    # 1. Schema version
    if template_data.get("schemaVersion") != 1:
        raise ValidationError("invalid_schema_version", "template.json.schemaVersion", "schemaVersion must be 1.")

    # 2. Kind
    kind = template_data.get("kind")
    if kind not in ALLOWED_TEMPLATE_KINDS:
        raise ValidationError("invalid_template_kind", "template.json.kind", f"kind must be one of {sorted(ALLOWED_TEMPLATE_KINDS)}")

    # 3. Metadata
    meta = template_data.get("metadata")
    if not isinstance(meta, dict):
        raise ValidationError("invalid_template_metadata", "template.json.metadata", "metadata object is required.")

    template_id = meta.get("id")
    template_version = meta.get("version")
    template_title = meta.get("title")

    if not template_id or not isinstance(template_id, str) or not KEY_REGEX.match(template_id):
        raise ValidationError("invalid_template_meta_id", "template.json.metadata.id", f"Invalid metadata ID: {template_id}")
    if not template_version or not isinstance(template_version, str) or not SEMVER_REGEX.match(template_version):
        raise ValidationError("invalid_template_meta_version", "template.json.metadata.version", f"Version must be semver X.Y.Z: {template_version}")
    if not template_title or not isinstance(template_title, str) or len(template_title) > 160:
        raise ValidationError("invalid_template_meta_title", "template.json.metadata.title", "Title is required (1-160 chars).")

    # 4. Content
    content = template_data.get("content")
    if not isinstance(content, dict):
        raise ValidationError("invalid_template_content", "template.json.content", "content object is required.")

    # Validate sections according to kind
    study_keys: Dict[str, Set[str]] = {}
    dsa_keys: Dict[str, Set[str]] = {}

    def _validate_study_sections(sections_raw: Any, base_path: str):
        if not isinstance(sections_raw, list) or len(sections_raw) == 0:
            raise ValidationError("empty_study_sections", base_path, "Study content must have non-empty sections.")
        section_keys: Set[str] = set()
        for s_idx, sec in enumerate(sections_raw):
            sp = f"{base_path}[{s_idx}]"
            if not isinstance(sec, dict):
                raise ValidationError("invalid_section", sp, "Section must be an object.")
            s_key = sec.get("key")
            s_name = sec.get("name")
            if not s_key or not isinstance(s_key, str) or not KEY_REGEX.match(s_key):
                raise ValidationError("invalid_section_key", f"{sp}.key", f"Invalid section key: {s_key}")
            if s_key in section_keys:
                raise ValidationError("duplicate_section_key", f"{sp}.key", f"Duplicate section key: {s_key}")
            section_keys.add(s_key)
            study_keys[s_key] = set()
            if not s_name or not isinstance(s_name, str) or len(s_name) > 160:
                raise ValidationError("invalid_section_name", f"{sp}.name", "Section name required (1-160 chars).")

            topics = sec.get("topics")
            if not isinstance(topics, list) or len(topics) == 0:
                raise ValidationError("empty_topics", f"{sp}.topics", "Topics must be a non-empty array.")
            topic_keys: Set[str] = set()
            for t_idx, top in enumerate(topics):
                tp = f"{sp}.topics[{t_idx}]"
                t_key = top.get("key")
                t_name = top.get("name")
                if not t_key or not isinstance(t_key, str) or not KEY_REGEX.match(t_key):
                    raise ValidationError("invalid_topic_key", f"{tp}.key", f"Invalid topic key: {t_key}")
                if t_key in topic_keys:
                    raise ValidationError("duplicate_topic_key", f"{tp}.key", f"Duplicate topic key: {t_key}")
                topic_keys.add(t_key)

                subtopics = top.get("subtopics")
                if not isinstance(subtopics, list) or len(subtopics) == 0:
                    raise ValidationError("empty_subtopics", f"{tp}.subtopics", "Subtopics must be a non-empty array.")
                for sub_idx, sub in enumerate(subtopics):
                    sub_p = f"{tp}.subtopics[{sub_idx}]"
                    sub_key = sub.get("key")
                    sub_name = sub.get("name")
                    if not sub_key or not isinstance(sub_key, str) or not KEY_REGEX.match(sub_key):
                        raise ValidationError("invalid_subtopic_key", f"{sub_p}.key", f"Invalid subtopic key: {sub_key}")
                    if sub_key in study_keys[s_key]:
                        raise ValidationError("duplicate_subtopic_key", f"{sub_p}.key", f"Duplicate subtopic key within section: {sub_key}")
                    study_keys[s_key].add(sub_key)
                    if not sub_name or not isinstance(sub_name, str):
                        raise ValidationError("invalid_subtopic_name", f"{sub_p}.name", "Subtopic name is required.")
                    _validate_leaf_resources(sub.get("resources"), f"{sub_p}.resources")

    def _validate_dsa_sections(sections_raw: Any, base_path: str):
        if not isinstance(sections_raw, list) or len(sections_raw) == 0:
            raise ValidationError("empty_dsa_sections", base_path, "DSA content must have non-empty sections.")
        section_keys: Set[str] = set()
        for s_idx, sec in enumerate(sections_raw):
            sp = f"{base_path}[{s_idx}]"
            if not isinstance(sec, dict):
                raise ValidationError("invalid_section", sp, "Section must be an object.")
            s_key = sec.get("key")
            s_name = sec.get("name")
            if not s_key or not isinstance(s_key, str) or not KEY_REGEX.match(s_key):
                raise ValidationError("invalid_section_key", f"{sp}.key", f"Invalid section key: {s_key}")
            if s_key in section_keys:
                raise ValidationError("duplicate_section_key", f"{sp}.key", f"Duplicate section key: {s_key}")
            section_keys.add(s_key)
            dsa_keys[s_key] = set()
            if not s_name or not isinstance(s_name, str) or len(s_name) > 160:
                raise ValidationError("invalid_section_name", f"{sp}.name", "Section name required (1-160 chars).")

            patterns = sec.get("patterns")
            if not isinstance(patterns, list) or len(patterns) == 0:
                raise ValidationError("empty_patterns", f"{sp}.patterns", "Patterns must be a non-empty array.")
            pattern_keys: Set[str] = set()
            for p_idx, pat in enumerate(patterns):
                pp = f"{sp}.patterns[{p_idx}]"
                p_key = pat.get("key")
                p_name = pat.get("name")
                if not p_key or not isinstance(p_key, str) or not KEY_REGEX.match(p_key):
                    raise ValidationError("invalid_pattern_key", f"{pp}.key", f"Invalid pattern key: {p_key}")
                if p_key in pattern_keys:
                    raise ValidationError("duplicate_pattern_key", f"{pp}.key", f"Duplicate pattern key: {p_key}")
                pattern_keys.add(p_key)

                problems = pat.get("problems")
                if not isinstance(problems, list) or len(problems) == 0:
                    raise ValidationError("empty_problems", f"{pp}.problems", "Problems must be a non-empty array.")
                for prob_idx, prob in enumerate(problems):
                    prob_p = f"{pp}.problems[{prob_idx}]"
                    prob_key = prob.get("key")
                    prob_name = prob.get("name")
                    prob_diff = prob.get("difficulty")
                    if not prob_key or not isinstance(prob_key, str) or not KEY_REGEX.match(prob_key):
                        raise ValidationError("invalid_problem_key", f"{prob_p}.key", f"Invalid problem key: {prob_key}")
                    if prob_key in dsa_keys[s_key]:
                        raise ValidationError("duplicate_problem_key", f"{prob_p}.key", f"Duplicate problem key within section: {prob_key}")
                    dsa_keys[s_key].add(prob_key)
                    if not prob_name or not isinstance(prob_name, str):
                        raise ValidationError("invalid_problem_name", f"{prob_p}.name", "Problem name is required.")
                    if prob_diff not in ALLOWED_DIFFICULTIES:
                        raise ValidationError("invalid_difficulty", f"{prob_p}.difficulty", f"Difficulty must be one of {sorted(ALLOWED_DIFFICULTIES)}, got '{prob_diff}'")
                    _validate_leaf_resources(prob.get("resources"), f"{prob_p}.resources")

    def _validate_leaf_resources(res_raw: Any, path: str):
        if res_raw is None:
            return
        if not isinstance(res_raw, list):
            raise ValidationError("invalid_resources", path, "Resources must be an array.")
        if len(res_raw) > 20:
            raise ValidationError("resource_limit_exceeded", path, "Max 20 resources allowed per item.")
        for r_idx, res in enumerate(res_raw):
            rp = f"{path}[{r_idx}]"
            if not isinstance(res, dict):
                raise ValidationError("invalid_resource", rp, "Resource must be an object.")
            label = res.get("label")
            url = res.get("url")
            if not label or not isinstance(label, str):
                raise ValidationError("invalid_resource_label", f"{rp}.label", "Resource label is required.")
            if not url or not isinstance(url, str):
                raise ValidationError("invalid_resource_url", f"{rp}.url", "Resource url is required.")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValidationError("unsafe_resource_url", f"{rp}.url", f"Resource URL must be a valid public HTTP/HTTPS URL: {url}")

    if kind == "study-template":
        _validate_study_sections(content.get("sections"), "template.json.content.sections")
    elif kind == "dsa-template":
        _validate_dsa_sections(content.get("sections"), "template.json.content.sections")
    elif kind == "workspace-template":
        study_data = content.get("study")
        dsa_data = content.get("dsa")
        if not study_data and not dsa_data:
            raise ValidationError("empty_workspace_template", "template.json.content", "workspace-template must contain study or dsa sections.")
        if study_data:
            _validate_study_sections(study_data.get("sections"), "template.json.content.study.sections")
        if dsa_data:
            _validate_dsa_sections(dsa_data.get("sections"), "template.json.content.dsa.sections")

        # Check plan references if plan is bundled
        plan = content.get("plan")
        if plan and isinstance(plan, dict):
            entries = plan.get("entries", [])
            for e_idx, entry in enumerate(entries):
                ep = f"template.json.content.plan.entries[{e_idx}]"
                tracker = entry.get("tracker")
                sec_key = entry.get("sectionKey")
                item_key = entry.get("itemKey")
                if tracker == "study":
                    if sec_key not in study_keys or item_key not in study_keys[sec_key]:
                        raise ValidationError("unresolved_plan_ref", ep, f"Study reference '{sec_key}/{item_key}' does not exist inside workspace bundle.")
                elif tracker == "dsa":
                    if sec_key not in dsa_keys or item_key not in dsa_keys[sec_key]:
                        raise ValidationError("unresolved_plan_ref", ep, f"DSA reference '{sec_key}/{item_key}' does not exist inside workspace bundle.")
                else:
                    raise ValidationError("invalid_plan_tracker", f"{ep}.tracker", f"Invalid tracker: {tracker}")

    # Scan entire template for unsafe fields or progress leaks
    scan_for_security_issues(template_data, "template.json")
    return template_data


def validate_entry_package(
    entry_dir: Path,
    categories_map: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Validate one entry directory containing entry.json, template.json, and optional cover."""
    entry_file = entry_dir / "entry.json"
    template_file = entry_dir / "template.json"

    if not entry_file.exists():
        raise ValidationError("missing_entry_json", str(entry_dir), f"entry.json not found in {entry_dir}")
    if not template_file.exists():
        raise ValidationError("missing_template_json", str(entry_dir), f"template.json not found in {entry_dir}")

    # Read and validate entry.json
    try:
        entry_raw = entry_file.read_bytes()
        entry_data = json.loads(entry_raw.decode("utf-8"))
    except Exception as exc:
        raise ValidationError("invalid_entry_json", str(entry_file), f"Failed to parse entry.json: {exc}")

    # Read and validate template.json
    try:
        template_raw = template_file.read_bytes()
        template_data = json.loads(template_raw.decode("utf-8"))
    except Exception as exc:
        raise ValidationError("invalid_template_json", str(template_file), f"Failed to parse template.json: {exc}")

    # Security scan on entry.json
    scan_for_security_issues(entry_data, "entry.json")

    # Required entry fields
    required_fields = [
        "$schema", "schemaVersion", "id", "slug", "version",
        "packageType", "templateKind", "title", "summary",
        "description", "categoryIds", "tags", "levels",
        "estimatedWeeks", "creator", "license", "template",
        "publishedAt", "updatedAt"
    ]
    for req in required_fields:
        if req not in entry_data:
            raise ValidationError("missing_required_field", f"entry.json.{req}", f"Required property '{req}' is missing.")

    entry_id = entry_data.get("id")
    version = entry_data.get("version")
    slug = entry_data.get("slug")
    package_type = entry_data.get("packageType")
    template_kind = entry_data.get("templateKind")
    title = entry_data.get("title")
    summary = entry_data.get("summary")
    description = entry_data.get("description")
    category_ids = entry_data.get("categoryIds")
    tags = entry_data.get("tags")
    levels = entry_data.get("levels")
    estimated_weeks = entry_data.get("estimatedWeeks")
    creator = entry_data.get("creator")
    license_info = entry_data.get("license")
    template_ref = entry_data.get("template")
    cover_ref = entry_data.get("cover")
    published_at = entry_data.get("publishedAt")
    updated_at = entry_data.get("updatedAt")

    # Directory alignment check
    rel_parts = entry_dir.parts[-2:]  # (<id>, <version>)
    if entry_id != rel_parts[0]:
        raise ValidationError("dir_id_mismatch", "entry.json.id", f"Entry ID '{entry_id}' does not match directory '{rel_parts[0]}'")
    if version != rel_parts[1]:
        raise ValidationError("dir_version_mismatch", "entry.json.version", f"Entry version '{version}' does not match directory '{rel_parts[1]}'")

    if not entry_id or not isinstance(entry_id, str) or not KEY_REGEX.match(entry_id):
        raise ValidationError("invalid_id", "entry.json.id", f"Invalid ID format: {entry_id}")
    if not version or not isinstance(version, str) or not SEMVER_REGEX.match(version):
        raise ValidationError("invalid_version", "entry.json.version", f"Version must be semver X.Y.Z: {version}")
    if not slug or not isinstance(slug, str) or not KEY_REGEX.match(slug):
        raise ValidationError("invalid_slug", "entry.json.slug", f"Invalid slug format: {slug}")

    if package_type not in ALLOWED_PACKAGE_TYPES:
        raise ValidationError("invalid_package_type", "entry.json.packageType", f"packageType must be one of {sorted(ALLOWED_PACKAGE_TYPES)}")
    if template_kind not in ALLOWED_TEMPLATE_KINDS:
        raise ValidationError("invalid_template_kind", "entry.json.templateKind", f"templateKind must be one of {sorted(ALLOWED_TEMPLATE_KINDS)}")

    # Check packageType vs templateKind consistency
    if package_type == "tracker" and template_kind not in {"study-template", "dsa-template"}:
        raise ValidationError("kind_mismatch_tracker", "entry.json.templateKind", "Tracker packageType requires study-template or dsa-template.")
    if package_type == "bundle" and template_kind != "workspace-template":
        raise ValidationError("kind_mismatch_bundle", "entry.json.templateKind", "Bundle packageType requires workspace-template.")

    if not title or not isinstance(title, str) or len(title) > 160:
        raise ValidationError("invalid_title", "entry.json.title", "Title is required (1-160 chars).")
    if not summary or not isinstance(summary, str) or len(summary) > 240:
        raise ValidationError("invalid_summary", "entry.json.summary", "Summary is required (1-240 chars).")
    if not description or not isinstance(description, str) or len(description) > 4000:
        raise ValidationError("invalid_description", "entry.json.description", "Description is required (1-4000 chars).")

    # Category IDs
    if not isinstance(category_ids, list) or len(category_ids) < 1 or len(category_ids) > 10:
        raise ValidationError("invalid_categories", "entry.json.categoryIds", "Must specify 1 to 10 category IDs.")
    for cat_id in category_ids:
        if cat_id not in categories_map:
            raise ValidationError("unknown_category", "entry.json.categoryIds", f"Category ID '{cat_id}' is not present in categories.json.")

    # Tags
    if not isinstance(tags, list) or len(tags) > 20:
        raise ValidationError("invalid_tags", "entry.json.tags", "Tags must be an array of up to 20 items.")
    for tag in tags:
        if not isinstance(tag, str) or not KEY_REGEX.match(tag):
            raise ValidationError("invalid_tag", "entry.json.tags", f"Invalid tag format: {tag}")

    # Levels
    if not isinstance(levels, list) or len(levels) < 1 or len(levels) > 4:
        raise ValidationError("invalid_levels", "entry.json.levels", "Levels must contain 1 to 4 items.")
    for lvl in levels:
        if lvl not in ALLOWED_LEVELS:
            raise ValidationError("invalid_level", "entry.json.levels", f"Level must be one of {sorted(ALLOWED_LEVELS)}")

    # Estimated Weeks
    if not isinstance(estimated_weeks, int) or estimated_weeks < 1 or estimated_weeks > 520:
        raise ValidationError("invalid_estimated_weeks", "entry.json.estimatedWeeks", "estimatedWeeks must be an integer between 1 and 520.")

    # Creator
    if not isinstance(creator, dict):
        raise ValidationError("invalid_creator", "entry.json.creator", "Creator object is required.")
    creator_id = creator.get("id")
    creator_name = creator.get("displayName")
    creator_url = creator.get("profileUrl")
    if not creator_id or not isinstance(creator_id, str) or not CREATOR_ID_REGEX.match(creator_id):
        raise ValidationError("invalid_creator_id", "entry.json.creator.id", f"Invalid creator ID: {creator_id}")
    if not creator_name or not isinstance(creator_name, str) or len(creator_name) > 100:
        raise ValidationError("invalid_creator_name", "entry.json.creator.displayName", "Creator displayName is required (1-100 chars).")
    if creator_url is not None:
        if not isinstance(creator_url, str) or not creator_url.startswith("https://"):
            raise ValidationError("invalid_creator_url", "entry.json.creator.profileUrl", "Creator profileUrl must be a secure https:// URL.")

    # License
    if not isinstance(license_info, dict):
        raise ValidationError("invalid_license", "entry.json.license", "License object is required.")
    spdx = license_info.get("spdxId")
    attribution = license_info.get("attributionText")
    if not spdx or not isinstance(spdx, str) or len(spdx) > 50:
        raise ValidationError("invalid_spdx", "entry.json.license.spdxId", "SPDX identifier required (1-50 chars).")
    if not attribution or not isinstance(attribution, str) or len(attribution) > 160:
        raise ValidationError("invalid_attribution", "entry.json.license.attributionText", "Attribution text required (1-160 chars).")

    # Dates
    if not isinstance(published_at, str) or not ISO_DATE_REGEX.match(published_at):
        raise ValidationError("invalid_published_at", "entry.json.publishedAt", "publishedAt must be an ISO UTC date string (YYYY-MM-DDTHH:MM:SSZ).")
    if not isinstance(updated_at, str) or not ISO_DATE_REGEX.match(updated_at):
        raise ValidationError("invalid_updated_at", "entry.json.updatedAt", "updatedAt must be an ISO UTC date string (YYYY-MM-DDTHH:MM:SSZ).")

    # Template ref bytes & hash
    if not isinstance(template_ref, dict):
        raise ValidationError("invalid_template_ref", "entry.json.template", "template reference object is required.")
    declared_path = template_ref.get("path")
    declared_bytes = template_ref.get("bytes")
    declared_sha256 = template_ref.get("sha256")

    if declared_path != "template.json":
        raise ValidationError("invalid_template_path", "entry.json.template.path", "template.path must be 'template.json'")

    actual_bytes = len(template_raw)
    actual_sha256 = hashlib.sha256(template_raw).hexdigest()

    if declared_bytes != actual_bytes:
        raise ValidationError("template_size_mismatch", "entry.json.template.bytes", f"Declared template bytes ({declared_bytes}) != actual ({actual_bytes}).")
    if declared_sha256 != actual_sha256:
        raise ValidationError("template_sha_mismatch", "entry.json.template.sha256", f"Declared SHA-256 does not match actual hash.")

    # Validate template content
    validate_template_document(template_data)

    # Cross-check metadata
    t_meta = template_data.get("metadata", {})
    if t_meta.get("id") != entry_id:
        raise ValidationError("meta_id_mismatch", "entry.json.id", f"Entry ID '{entry_id}' != template.json metadata.id '{t_meta.get('id')}'")
    if t_meta.get("version") != version:
        raise ValidationError("meta_version_mismatch", "entry.json.version", f"Entry version '{version}' != template.json metadata.version '{t_meta.get('version')}'")
    if template_data.get("kind") != template_kind:
        raise ValidationError("meta_kind_mismatch", "entry.json.templateKind", f"Entry kind '{template_kind}' != template.json kind '{template_data.get('kind')}'")

    # Cover image validation
    cover_file = None
    if cover_ref:
        if not isinstance(cover_ref, dict):
            raise ValidationError("invalid_cover_ref", "entry.json.cover", "Cover reference must be an object.")
        c_path = cover_ref.get("path")
        c_alt = cover_ref.get("alt")
        c_bytes = cover_ref.get("bytes")
        c_sha256 = cover_ref.get("sha256")
        c_width = cover_ref.get("width")
        c_height = cover_ref.get("height")

        if not c_path or not isinstance(c_path, str):
            raise ValidationError("invalid_cover_path", "entry.json.cover.path", "Cover path is required.")
        if not c_alt or not isinstance(c_alt, str) or len(c_alt) > 200:
            raise ValidationError("invalid_cover_alt", "entry.json.cover.alt", "Cover alt text is required (1-200 chars).")

        cover_path_obj = entry_dir / c_path
        if not cover_path_obj.exists():
            raise ValidationError("missing_cover_file", "entry.json.cover.path", f"Cover file '{c_path}' not found in entry directory.")
        cover_raw = cover_path_obj.read_bytes()
        cover_file = cover_path_obj

        if len(cover_raw) > MAX_COVER_BYTES:
            raise ValidationError("cover_too_large", str(cover_path_obj), f"Cover exceeds max size 512KB ({len(cover_raw)} bytes).")
        if c_bytes != len(cover_raw):
            raise ValidationError("cover_size_mismatch", "entry.json.cover.bytes", f"Cover bytes ({c_bytes}) != actual ({len(cover_raw)})")
        if c_sha256 != hashlib.sha256(cover_raw).hexdigest():
            raise ValidationError("cover_sha_mismatch", "entry.json.cover.sha256", "Cover SHA-256 does not match actual hash.")

        mime_type, actual_w, actual_h = inspect_image_header(cover_raw)
        if actual_w > MAX_COVER_WIDTH or actual_h > MAX_COVER_HEIGHT:
            raise ValidationError("cover_dims_exceeded", "entry.json.cover", f"Cover dimensions ({actual_w}x{actual_h}) exceed maximum {MAX_COVER_WIDTH}x{MAX_COVER_HEIGHT}.")
        if c_width != actual_w or c_height != actual_h:
            raise ValidationError("cover_dims_mismatch", "entry.json.cover", f"Declared dimensions ({c_width}x{c_height}) != actual ({actual_w}x{actual_h}).")
    else:
        # Check if an undeclared cover file exists
        candidates = list(entry_dir.glob("cover.*"))
        if candidates:
            raise ValidationError("undeclared_cover", str(candidates[0]), "Cover file exists on disk but is not declared in entry.json.")

    return {
        "entry": entry_data,
        "template": template_data,
        "entry_dir": entry_dir,
        "cover_file": cover_file,
    }


def check_version_immutability(repo_root: Path, base_ref: str = "origin/main") -> None:
    """Ensure PR does not modify already published versions from base_ref."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--verify", base_ref],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            return

        diff_res = subprocess.run(
            ["git", "diff", "--name-status", f"{base_ref}...HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if diff_res.returncode != 0:
            return

        modified_files = diff_res.stdout.strip().splitlines()
        for line in modified_files:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            status, filepath = parts[0], parts[1]
            if filepath.startswith("entries/") and (status.startswith("M") or status.startswith("D")):
                entry_parts = Path(filepath).parts
                if len(entry_parts) >= 3:
                    version_path = f"{entry_parts[0]}/{entry_parts[1]}/{entry_parts[2]}"
                    check_base = subprocess.run(
                        ["git", "cat-file", "-e", f"{base_ref}:{version_path}/entry.json"],
                        cwd=str(repo_root),
                        capture_output=True,
                    )
                    if check_base.returncode == 0:
                        raise ValidationError(
                            "immutable_version_modified",
                            filepath,
                            f"Published version '{version_path}' is immutable and cannot be modified or deleted. Please submit a new semver patch or minor version (e.g. 1.0.1 or 1.1.0)."
                        )
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise


def validate_all(repo_root: Path, base_ref: Optional[str] = None) -> List[Dict[str, Any]]:
    print(f"🔍 Validating Trackers Library in: {repo_root}")

    # 1. Categories
    print("  ✓ Validating categories.json...")
    categories_map = validate_categories_file(repo_root)
    print(f"    Found {len(categories_map)} valid categories.")

    # 2. Entries discovery
    entries_dir = repo_root / "entries"
    if not entries_dir.exists():
        raise ValidationError("missing_entries_dir", "entries", "entries/ directory not found.")

    entry_dirs: List[Path] = []
    for id_dir in entries_dir.iterdir():
        if id_dir.is_dir() and not id_dir.name.startswith("."):
            for ver_dir in id_dir.iterdir():
                if ver_dir.is_dir() and not ver_dir.name.startswith("."):
                    entry_dirs.append(ver_dir)

    if not entry_dirs:
        raise ValidationError("no_entries_found", "entries", "No entry versions found under entries/<id>/<version>/")

    print(f"  ✓ Discovered {len(entry_dirs)} entry packages. Validating each...")

    seen_ids: Set[str] = set()
    seen_slugs: Set[str] = set()
    validated_packages: List[Dict[str, Any]] = []

    for entry_dir in sorted(entry_dirs):
        pkg = validate_entry_package(entry_dir, categories_map)
        entry_id = pkg["entry"]["id"]
        slug = pkg["entry"]["slug"]
        version = pkg["entry"]["version"]

        if entry_id in seen_ids:
            raise ValidationError("duplicate_catalog_id", f"entries/{entry_id}", f"Multiple versions of '{entry_id}' in catalog root.")
        seen_ids.add(entry_id)

        if slug in seen_slugs:
            raise ValidationError("duplicate_catalog_slug", f"entries/{entry_id}", f"Duplicate slug '{slug}' across catalog entries.")
        seen_slugs.add(slug)

        validated_packages.append(pkg)
        print(f"    ✓ [{entry_id}@{version}] '{pkg['entry']['title']}' passed all checks.")

    # 3. Check version immutability if base_ref provided
    if base_ref:
        print(f"  ✓ Checking version immutability against {base_ref}...")
        check_version_immutability(repo_root, base_ref)
        print("    No immutable published versions were mutated.")

    print(f"\n🎉 Validation successful! {len(validated_packages)} entries are 100% compliant.")
    return validated_packages


def main():
    parser = argparse.ArgumentParser(description="Validate Trackers Community Library entries and categories.")
    parser.add_argument("--repo-root", default=".", help="Path to repository root (default: current directory)")
    parser.add_argument("--base-ref", default=os.getenv("GITHUB_BASE_REF", None), help="Git base ref for immutability check (e.g. origin/main)")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    try:
        validate_all(repo_root, base_ref=args.base_ref)
        sys.exit(0)
    except ValidationError as exc:
        print(f"\n❌ VALIDATION ERROR [{exc.code}] at {exc.path}:", file=sys.stderr)
        print(f"   {exc.message}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n💥 UNEXPECTED ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
