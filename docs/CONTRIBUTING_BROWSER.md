# Step-by-Step Contribution Guide (100% In Your Browser)

You do **not** need to install Git, Python, or know any terminal commands to submit a learning track or DSA sheet to Trackers! You can do everything directly on the GitHub website.

Follow these 5 simple steps:

---

## Step 1: Prepare Your Curriculum JSON

You need the JSON file for your curriculum (e.g. from the Trackers AI Prompt Builder or an LLM like ChatGPT or Claude).

Save this JSON text on your computer (for example, in a text editor or Notepad) so you have it ready to paste.

> 💡 **Structure Note:** Each tracker should have **exactly 1 section** in its `sections` list. Use `topics` (for Study) or `patterns` (for DSA) to organize subject areas so that it fits smoothly into any user's account without hitting section limits.

Study subtopics and DSA problems can each include a primary `url` and up to 20
`resources` containing `label` and `url`. See the [complete linked example](examples/linked-workspace-template.json)
and [link and cover requirements](../CONTRIBUTING.md). Use HTTP(S) links without
credentials. Leave personal notes and progress out of the template. One optional
16:9 cover image supplies both the thumbnail and detail artwork.

---

## Step 2: Fork the Repository

1. Go to the main repository page: **[github.com/armanavasthi/trackers-library](https://github.com/armanavasthi/trackers-library)**.
2. In the top-right corner of the page, click the **Fork** button (looks like a branch icon).
3. On the next screen, leave the default settings and click **Create fork**.
4. You will now be on your own personal copy of the repository (e.g., `github.com/your-username/trackers-library`).

---

## Step 3: Add Your `template.json`

1. In your forked repository, click the **Add file** dropdown button (near the top right of the file list) and select **Create new file**.
2. In the filename box (where it says *Name your file...*), type:
   ```text
   entries/your-track-name/1.0.0/template.json
   ```
   *(Replace `your-track-name` with your topic in lowercase with hyphens, like `system-design-basics` or `react-patterns`).*  
   > 💡 **Tip:** Typing the slashes `/` will automatically create the folders for you!

3. In the large text area below, paste your curriculum JSON text.
4. Scroll down to the bottom, select **Commit changes...** (or **Commit directly to main**), and click **Commit changes**.

---

## Step 4: Add Your `entry.json` (Catalog Info)

Every curriculum needs a companion `entry.json` that provides the title, author name, and categories.

1. Click **Add file** ➔ **Create new file** again.
2. In the filename box, type:
   ```text
   entries/your-track-name/1.0.0/entry.json
   ```
   *(Use the exact same `your-track-name` and `1.0.0` folder name from Step 3).*
3. Copy and paste this template, filling in your details:

```json
{
  "$schema": "https://trackers.example/schemas/learning-library-entry-v1.json",
  "schemaVersion": 1,
  "id": "your-track-name",
  "slug": "your-track-name",
  "version": "1.0.0",
  "packageType": "tracker",
  "templateKind": "study-template",
  "title": "Your Track Title Here",
  "summary": "A 1-2 sentence summary of what this curriculum covers.",
  "description": "A detailed description explaining who this is for and what will be learned.",
  "categoryIds": ["software-engineering"],
  "tags": ["beginner", "foundations"],
  "levels": ["beginner"],
  "estimatedWeeks": 4,
  "creator": {
    "id": "your-github-username",
    "displayName": "Your Name",
    "profileUrl": "https://github.com/your-github-username"
  },
  "license": {
    "spdxId": "MIT",
    "attributionText": "Your Name"
  },
  "template": {
    "path": "template.json",
    "sha256": "TO_BE_CALCULATED",
    "bytes": 1000
  },
  "publishedAt": "2026-10-16T00:00:00Z",
  "updatedAt": "2026-10-16T00:00:00Z"
}
```

> 🏷️ **Allowed Categories:** Choose 1 or 2 from: `dsa-algorithms`, `software-engineering`, `system-design`, `ai-data`, `interview-preparation`, `career-foundations`, `general-learning`.  
> 📊 **Allowed Levels:** Choose from: `beginner`, `intermediate`, `advanced`, `mixed`.  
> 🔢 **SHA-256 and Bytes:** If you don't know how to compute these, leave temporary values or ask in the Pull Request—our automated GitHub reviewer will tell you the exact numbers to paste!

4. Scroll down and click **Commit changes**.

---

## Step 5: Open the Pull Request

1. Go to the top of your repository and click the **Pull requests** tab.
2. Click the green **New pull request** button.
3. You will see a comparison screen showing the files you added. Click **Create pull request**.
4. Give your PR a clear title (e.g. `feat: add Python for Beginners study track`) and click **Create pull request**.

---

## What Happens Next? 🤖

* Our **Automated Robot Reviewer** will immediately run checks on your submission.
* In about 1 minute, you will see either:
  * ✅ **All checks have passed** (Green checkmark): Everything is perfectly formatted! The maintainers will review and merge it.
  * ❌ **Some checks were not successful** (Red X): Click on **Details** to see what needs adjusting (such as correcting the SHA-256 hash or fixing a typo).
* Once merged, your track will be automatically published and become visible to all Trackers users worldwide within **24 hours**!
