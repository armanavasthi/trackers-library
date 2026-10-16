# Contributing to Trackers Community Library

Thank you for contributing to the **Trackers Community Library**! This repository hosts curated study tracks, DSA sheets, and learning workspaces available directly in the Trackers application.

To ensure high quality, deterministic builds, and safe distribution to thousands of users, **all pull requests are automatically validated by CI**.

---

## 🚀 Quick Start: Submitting a Track

### 1. Structure Your Entry
Every track or workspace bundle lives under `entries/<id>/<version>/`:

```
entries/
└── your-track-id/
    └── 1.0.0/
        ├── entry.json        # Metadata, author, license, tags, categories
        ├── template.json     # Curated syllabus, topics/problems, resources
        └── cover.png         # (Optional) 1200x800 or 1600x900 cover artwork
```

- `<id>`: Unique lowercase kebab-case identifier (e.g. `system-design-primer`, `blind-75-plus`).
- `<version>`: Semantic version (`1.0.0`, `1.1.0`, etc.).

---

## 📋 Required Files & Rules

### 1. `template.json`
Your `template.json` is a reusable Trackers template (`schemaVersion: 1`).
- **Kinds**:
  - `study-template`: Structured study tracker (topics, subtopics, study resources).
  - `dsa-template`: Problem-solving tracker with difficulty ratings (`easy`, `medium`, `hard`).
  - `workspace-template`: Complete learning bundle (combining study tracks, DSA tracks, and an optional Day 1–Day N milestone plan).
- **Single Section Structure**:
  - Each tracker (`study-template` or `dsa-template`) must have **exactly 1 section** in `content.sections`.
  - Use `topics` (Study) or `patterns` (DSA) to organize major domains and problem categories so installed tracks fit cleanly into users' accounts without hitting section capacity limits.
- **Cleanliness**:
  - Reusable templates must **never** contain personal account data or progress states (`status`, `confidence`, `history`, `preferences`, `storagePath`).
  - All resource URLs must be valid, publicly accessible HTTPS/HTTP links.

### 2. `entry.json`
Your `entry.json` provides catalog metadata matching [learning-library-entry-v1.schema.json](schemas/learning-library-entry-v1.schema.json):

```json
{
  "$schema": "https://trackers.example/schemas/learning-library-entry-v1.json",
  "schemaVersion": 1,
  "id": "your-track-id",
  "slug": "your-track-id",
  "version": "1.0.0",
  "packageType": "tracker",
  "templateKind": "dsa-template",
  "title": "Your Track Title",
  "summary": "Short 1-sentence summary under 240 characters.",
  "description": "Comprehensive overview of the curriculum and learning outcomes.",
  "categoryIds": ["dsa-algorithms", "interview-preparation"],
  "tags": ["arrays", "trees", "graphs"],
  "levels": ["beginner", "intermediate"],
  "estimatedWeeks": 6,
  "creator": {
    "id": "your-handle",
    "displayName": "Your Name",
    "profileUrl": "https://github.com/your-handle"
  },
  "license": {
    "spdxId": "MIT",
    "attributionText": "Your Name or Organization"
  },
  "template": {
    "path": "template.json",
    "sha256": "<computed-sha256>",
    "bytes": 1234
  },
  "publishedAt": "2026-10-04T00:00:00Z",
  "updatedAt": "2026-10-04T00:00:00Z"
}
```

> 💡 **Tip:** Category IDs must match the canonical list defined in [`categories.json`](categories.json).

### 3. Optional Cover Art
- Formats: PNG, JPEG, or WebP.
- Max file size: 512 KB.
- Recommended dimensions: 1200×800 or 1600×900 px (Max: 2400×1600 px).
- If included, compute `bytes`, `sha256`, `width`, and `height` in `entry.json.cover`.

---

## 🛠️ Local Verification Before Submitting

Run the built-in zero-dependency validation script:

```bash
# Validate your entries against all schemas and integrity rules
python3 scripts/validate.py

# Test the deterministic catalog build
python3 scripts/build.py
```

If both commands exit successfully with `100% compliant`, your PR is ready to merge!

---

## 🔒 Automated CI Review Checks

GitHub Actions automatically verifies:
1. **Schema Compliance**: `entry.json` and `template.json` strictly match JSON Schemas.
2. **SHA-256 & Byte Integrity**: Declared hashes match the physical files byte-for-byte.
3. **Reference Integrity**: All category IDs exist in `categories.json`; all bundle plan entries point to valid sections/problems.
4. **Security & Sanitization**: No credentials/secrets, no raw `<script>` or HTML tags, no prototype pollution.
5. **Version Immutability**: Existing published versions cannot be mutated or deleted. To update content, increment the semver (e.g. `1.0.1` or `1.1.0`).
