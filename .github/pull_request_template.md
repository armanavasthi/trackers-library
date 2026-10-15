### 📦 Track / Bundle Submission Checklist

Please verify the following before submitting:

- [ ] **Directory Structure**: Entry placed under `entries/<id>/<version>/` with valid lowercase kebab-case ID and semantic version.
- [ ] **Metadata**: `entry.json` has complete title, summary, description, author, license, and categories from `categories.json`.
- [ ] **Clean Template**: `template.json` contains only curated curricula (no user progress/status/history).
- [ ] **Hash & Size Verification**: `template.sha256` and `template.bytes` in `entry.json` match `template.json` exactly.
- [ ] **Cover Image (if applicable)**: Cover image is under 512KB and dimensions are valid WebP, PNG, or JPEG.
- [ ] **Local Validation**: Ran `python3 scripts/validate.py` and `python3 scripts/build.py` locally and all checks passed.

---

### Description of Changes / New Content
<!-- Provide a brief overview of what this track/sheet covers and who it is for -->
