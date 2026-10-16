# Trackers Community Library 📚

The official community-driven catalog of curated learning tracks, system design curricula, and DSA problem sets for **[Trackers](https://github.com/armanavasthi/trackers)**.

Any track merged into this repository is automatically built, cryptographically verified, and published to GitHub Pages to be served directly inside the Trackers application.

---

## 🌐 Live Catalog & Directory

* **Landing Page & Directory:** [https://armanavasthi.github.io/trackers-library/](https://armanavasthi.github.io/trackers-library/)
* **Catalog API Manifest:** `https://armanavasthi.github.io/trackers-library/catalog-v1.json`
* **Artifact Base URL:** `https://armanavasthi.github.io/trackers-library/artifacts/{id}/{version}/template.json`

---

## 🤝 How to Contribute a Learning Track or DSA Sheet

Anyone is welcome to submit a curriculum! Choose the guide that best matches your comfort level:

```
┌───────────────────────────────────────┬───────────────────────────────────────┐
│ 💻 Option A: For Developers           │ 🌐 Option B: For Non-Technical Users  │
│ (Using Terminal, Git & Python)        │ (100% in Browser, No Installation)    │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

---

### Option A: For Developers (Terminal & Git Workflow)

If you are comfortable with Git and command-line tools:

#### 1. Fork & Clone
```bash
git clone https://github.com/<your-username>/trackers-library.git
cd trackers-library
git checkout -b add-my-track
```

#### 2. Create Your Track Folder
Every submission lives under `entries/<track-id>/<version>/`:
```text
entries/
└── your-track-id/
    └── 1.0.0/
        ├── template.json   # Reusable curriculum (study or DSA)
        └── entry.json      # Metadata, tags, license, sha256 & byte size
```

#### 3. Test & Validate Locally
Before submitting, run the zero-dependency repository validator:
```bash
python3 scripts/validate.py
```
If it reports `100% compliant`, your files adhere to all schemas and integrity rules!

#### 4. Commit, Push & Open PR
```bash
git add .
git commit -m "feat: add <your-track-id> 1.0.0 curriculum"
git push origin add-my-track
```
Then open a Pull Request on GitHub. The automated CI gate will verify your submission.  
*(See [CONTRIBUTING.md](./CONTRIBUTING.md) for full metadata specifications).*

---

### Option B: For Non-Technical Contributors (100% In-Browser)

You don't need to install Git, Python, or open a terminal! You can submit a curriculum directly using GitHub’s web interface in 5 minutes:

1. **Have your JSON ready:** Copy your generated curriculum JSON (e.g., from the Trackers AI Prompt Builder or ChatGPT).
2. **Fork the repo:** Go to the top of this page and click **Fork** ➔ **Create fork**.
3. **Add files:**
   - In your fork, click **Add file** ➔ **Create new file**.
   - Type `entries/your-track-name/1.0.0/template.json` in the filename box (typing slashes `/` creates folders automatically).
   - Paste your curriculum JSON and click **Commit changes**.
   - Repeat the step to create `entries/your-track-name/1.0.0/entry.json` with the title, description, and author info.
4. **Open a Pull Request:** Go to **Pull requests** ➔ **New pull request** ➔ **Create pull request**.
5. **Automated Review:** GitHub Actions will immediately check your submission and show a green checkmark ✅ when ready!

👉 **[Read the complete click-by-click Browser Guide with screenshots & templates](./docs/CONTRIBUTING_BROWSER.md)**

---

## 🛡️ Automated Quality & Security Gate

Every Pull Request is tested automatically by GitHub Actions to guarantee high quality and minimal human review:

1. **Schema Validation:** Strict conformance against `trackers-template-v1` and `learning-library-entry-v1`.
2. **Cryptographic Integrity:** SHA-256 hashes and byte lengths must match files exactly.
3. **Zero Secrets / Zero XSS:** Content is scanned to block passwords, tokens, API keys, and unsafe raw HTML tags.
4. **Immutability:** Once a version (e.g. `1.0.0`) is published, it cannot be edited or deleted—updates require incrementing the semver (e.g. `1.0.1` or `1.1.0`).

---

## 📄 License

The catalog code and schemas are licensed under the [MIT License](./LICENSE). Curricula are licensed individually by their authors under open-source licenses specified in each `entry.json`.
