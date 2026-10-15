# Trackers Learning Library Catalog

The official community-driven catalog of learning roadmaps, algorithm problem sets, and study tracks for **Trackers**.

---

## 📖 How It Works

This repository hosts the static JSON catalog and artifacts for Trackers.
When changes are merged into `main`, GitHub Actions validates every entry and automatically publishes the updated catalog to **GitHub Pages**.

### Catalog Endpoints
- **Live Catalog Manifest:** `https://<your-org-or-username>.github.io/trackers-library/catalog-v1.json`
- **Artifact URL Base:** `https://<your-org-or-username>.github.io/trackers-library/artifacts/{entry-id}/{version}/template.json`

---

## 🛠️ Automated CI/CD & Gatekeeping

To keep human review minimal and maintain strict quality standards, every Pull Request is automatically validated by GitHub Actions against:

1. **Schema Conformance**: Validates against standard JSON Schemas (`schemas/`).
2. **Deterministic Checksums**: Verifies SHA-256 hashes and byte lengths.
3. **Reference Integrity**: Ensures all subtopics, problems, categories, and planner references resolve cleanly.
4. **Content Security**: Strips/rejects script tags and raw HTML injections in descriptions.
5. **Version Immutability**: Prohibits editing already-published versions—new edits must bump the version number.

---

## 🚀 How to Contribute a Tracker or Bundle

We welcome community-contributed study tracks, DSA sheets, and guided learning roadmaps!

See **[CONTRIBUTING.md](./CONTRIBUTING.md)** for detailed instructions on authoring, testing locally, and submitting a Pull Request.

---

## 📄 License

Catalog metadata and templates are licensed under [MIT](./LICENSE).
Individual templates may declare specific open-source licenses (e.g., MIT, CC-BY-4.0) inside their `entry.json`.
