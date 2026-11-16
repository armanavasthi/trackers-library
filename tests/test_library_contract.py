"""Focused package-to-publication compatibility checks (standard library only)."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build import build_catalog, compute_content_counts
from validate import RETIRED_DEMO_FILES, ValidationError, check_version_immutability, validate_categories_file, validate_entry_package, validate_template_document


def example():
    return json.loads((ROOT / "docs/examples/linked-workspace-template.json").read_text())


def leaves(template):
    content = template["content"]
    return (
        content["study"]["sections"][0]["topics"][0]["subtopics"][0],
        content["dsa"]["sections"][0]["patterns"][0]["problems"][0],
    )


def png_bytes(width=160, height=90):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\x80\xff" * width) * height))
        + chunk(b"IEND", b"")
    )


class LibraryContractTests(unittest.TestCase):
    def test_published_templates_reject_malformed_fields_before_install(self):
        problem = ("content", "dsa", "sections", 0, "patterns", 0, "problems", 0)
        topic = ("content", "study", "sections", 0, "topics", 0)
        cases = [
            (("kind",), []), (("schemaVersion",), True), (("unexpected",), True),
            (("metadata", "title"), "   "), (("metadata", "unexpected"), True),
            (("content", "study"), None), (topic, 3),
            (topic + ("name",), "   "),
            (problem + ("difficulty",), []),
            (problem + ("name",), "x" * 161),
        ]
        for value in (None, True, 0, -1, 1.5, 1441):
            cases.append((problem + ("estimatedMinutes",), value))
        for path, value in cases:
            template = example()
            target = template
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValidationError):
                validate_template_document(template)

    def test_dsa_difficulty_can_be_omitted_like_the_app_contract(self):
        template = example()
        del leaves(template)[1]["difficulty"]
        self.assertIs(validate_template_document(template), template)

    def test_bundled_planner_contract_rejects_bad_or_duplicate_entries(self):
        entry = {"tracker": "study", "sectionKey": "study", "itemKey": "hash-tables", "dayOffset": 0}
        template = example()
        template["content"]["plan"] = {"anchor": "user-selected-start-date", "entries": [entry]}
        self.assertIs(validate_template_document(template), template)
        for field, value in (("dayOffset", -1), ("dayOffset", True), ("dayOffset", 366), ("tracker", []), ("estimatedMinutes", 0), ("note", "")):
            invalid = copy.deepcopy(template)
            invalid["content"]["plan"]["entries"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                validate_template_document(invalid)
        template["content"]["plan"]["entries"].append(copy.deepcopy(entry))
        with self.assertRaises(ValidationError) as failure:
            validate_template_document(template)
        self.assertEqual(failure.exception.code, "duplicate_plan_entry")

    def test_optional_dsa_sub_pattern_in_standalone_and_workspace(self):
        for sub in ("Sliding Window", "x" * 200, "😀" * 200):
            template = example()
            leaves(template)[1]["sub"] = sub
            with self.subTest(sub=sub):
                self.assertIs(validate_template_document(template), template)
                template["kind"] = "dsa-template"
                template["content"] = template["content"]["dsa"]
                self.assertIs(validate_template_document(template), template)

    def test_invalid_dsa_sub_pattern_is_rejected(self):
        for sub in (None, 3, True, [], {}, "", "   ", "x" * 201, "😀" * 201):
            template = example()
            leaves(template)[1]["sub"] = sub
            with self.subTest(sub=sub), self.assertRaises(ValidationError) as failure:
                validate_template_document(template)
            self.assertEqual(failure.exception.code, "invalid_sub_pattern")

    def test_sub_pattern_is_not_a_study_field(self):
        template = example()
        leaves(template)[0]["sub"] = "Sliding Window"
        with self.assertRaises(ValidationError) as failure:
            validate_template_document(template)
        self.assertEqual(failure.exception.code, "unknown_field")

    def test_only_exact_retired_demo_deletions_bypass_immutability(self):
        for filepath in RETIRED_DEMO_FILES:
            with self.subTest(filepath=filepath), patch('validate.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0),
                SimpleNamespace(returncode=0, stdout=f'D\t{filepath}\n'),
            ]):
                check_version_immutability(ROOT)
        for status, filepath in (
            ('M', next(iter(RETIRED_DEMO_FILES))),
            ('D', 'entries/senior-swe-system-design-and-backend-mastery/1.0.0/template.json'),
            ('D', 'entries/dsa-fundamentals/1.0.1/template.json'),
            ('D', 'entries/dsa-fundamentals/1.0.0/cover.png'),
        ):
            with self.subTest(status=status, filepath=filepath), patch('validate.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0),
                SimpleNamespace(returncode=0, stdout=f'{status}\t{filepath}\n'),
                SimpleNamespace(returncode=0),
            ]):
                with self.assertRaises(ValidationError) as failure:
                    check_version_immutability(ROOT)
                self.assertEqual(failure.exception.code, 'immutable_version_modified')

    def test_study_dsa_and_workspace_accept_primary_and_all_labelled_links(self):
        template = example()
        self.assertIs(validate_template_document(template), template)
        for tracker in ("study", "dsa"):
            with self.subTest(tracker=tracker):
                standalone = copy.deepcopy(template)
                standalone["kind"] = tracker + "-template"
                standalone["content"] = standalone["content"][tracker]
                self.assertIs(validate_template_document(standalone), standalone)

    def test_primary_and_resource_urls_share_safety_limits(self):
        invalid = (
            None, 123, "", "javascript:alert(1)", "//example.com", "https://", "HTTPS://example.com",
            "https://user:password@example.com", "https://@example.com",
            "https://example.com/has space", "https://example.com/\npath",
            "https://example.com\\@other.example", "https://[broken",
            "https://example.com:99999", "https://example.com/" + "x" * 2048,
        )
        for index in (0, 1):
            for url in invalid:
                for field in ("url", "resources"):
                    with self.subTest(tracker=index, field=field, url=url):
                        template = example()
                        leaf = leaves(template)[index]
                        leaf[field] = url if field == "url" else [{"label": "Reference", "url": url}]
                        with self.assertRaises(ValidationError):
                            validate_template_document(template)

    def test_optional_links_and_progress_rejection(self):
        template = example()
        for leaf in leaves(template):
            leaf.pop("url")
            leaf.pop("resources")
        validate_template_document(template)
        for field in ("notes", "status", "history", "attempts"):
            with self.subTest(field=field):
                modified = copy.deepcopy(template)
                leaves(modified)[0][field] = "personal data"
                with self.assertRaises(ValidationError):
                    validate_template_document(modified)

    def test_link_counts_deduplicate_per_leaf_and_keep_resource_limit(self):
        template = example()
        for leaf in leaves(template):
            leaf["resources"].append({"label": "Primary again", "url": leaf["url"]})
        self.assertEqual(compute_content_counts(template)[0]["resources"], 6)
        for tracker in ("study", "dsa"):
            standalone = {**template, "kind": tracker + "-template", "content": template["content"][tracker]}
            self.assertEqual(compute_content_counts(standalone)[0]["resources"], 3)
        leaf = leaves(template)[0]
        leaf["resources"] = [{"label": f"Reference {index}", "url": f"https://example.com/{index}"} for index in range(20)]
        validate_template_document(template)
        leaf["resources"].append(leaf["resources"][0])
        with self.assertRaises(ValidationError):
            validate_template_document(template)

    def test_duplicate_resources_and_unknown_leaf_fields_are_rejected(self):
        for leaf_index in (0, 1):
            template = example()
            leaf = leaves(template)[leaf_index]
            leaf["resources"].append({"label": "Repeated reference", "url": leaf["resources"][0]["url"]})
            with self.subTest(leaf_index=leaf_index, kind="duplicate"):
                with self.assertRaises(ValidationError) as failure:
                    validate_template_document(template)
                self.assertEqual(failure.exception.code, "duplicate_resource_url")
            for field in ("notes", "rootUrl", "custom"):
                for target in ("leaf", "resource"):
                    with self.subTest(leaf_index=leaf_index, field=field, target=target):
                        template = example()
                        leaf = leaves(template)[leaf_index]
                        value = leaf if target == "leaf" else leaf["resources"][0]
                        value[field] = "unsupported"
                        with self.assertRaises(ValidationError) as failure:
                            validate_template_document(template)
                        self.assertEqual(failure.exception.code, "unknown_field")

    def test_explicit_null_resources_are_rejected(self):
        for leaf_index in (0, 1):
            with self.subTest(leaf_index=leaf_index):
                template = example()
                leaves(template)[leaf_index]["resources"] = None
                with self.assertRaises(ValidationError):
                    validate_template_document(template)

    def test_build_publishes_versioned_paths_preserving_bytes_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            shutil.copy2(ROOT / "categories.json", repo / "categories.json")
            shutil.copytree(ROOT / "schemas", repo / "schemas")
            directory = repo / "entries" / "linked-learning" / "1.0.0"
            directory.mkdir(parents=True)
            template = example()
            raw = (json.dumps(template, indent=2) + "\n").encode()
            (directory / "template.json").write_bytes(raw)
            cover = png_bytes()
            (directory / "cover.png").write_bytes(cover)
            entry = json.loads(next((ROOT / "entries").glob("*/*/entry.json")).read_text())
            entry.update(id="linked-learning", slug="linked-learning", version="1.0.0", packageType="bundle", templateKind="workspace-template")
            entry["template"] = {"path": "template.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            entry["cover"] = {"path": "cover.png", "alt": "Course cover", "bytes": len(cover), "sha256": hashlib.sha256(cover).hexdigest(), "width": 160, "height": 90}
            authored = json.dumps(entry).encode()
            (directory / "entry.json").write_bytes(authored)
            build_catalog(repo, repo / "dist")
            published = json.loads((repo / "dist/catalog-v1.json").read_text())["entries"][0]
            for key, expected in (("template", raw), ("cover", cover)):
                path = published[key]["path"]
                self.assertEqual(path, f"artifacts/linked-learning/1.0.0/{entry[key]['path']}")
                self.assertEqual((repo / "dist" / path).read_bytes(), expected)
            self.assertEqual(published["contentCounts"]["resources"], 6)
            self.assertEqual(json.loads((repo / "dist" / published["template"]["path"]).read_text()), template)
            self.assertEqual((directory / "entry.json").read_bytes(), authored)
            # Match both metadata schemas' decimal 512,000-byte limit exactly.
            for byte_count in (512000, 512001):
                padded_cover = cover + b"\0" * (byte_count - len(cover))
                (directory / "cover.png").write_bytes(padded_cover)
                entry["cover"].update(bytes=byte_count, sha256=hashlib.sha256(padded_cover).hexdigest())
                (directory / "entry.json").write_text(json.dumps(entry))
                if byte_count == 512000:
                    validate_entry_package(directory, validate_categories_file(repo))
                else:
                    with self.assertRaises(ValidationError) as failure:
                        validate_entry_package(directory, validate_categories_file(repo))
                    self.assertEqual(failure.exception.code, "cover_too_large")
            # Authored cover paths cannot read files outside the entry directory.
            entry["cover"]["path"] = "../cover.png"
            (directory / "entry.json").write_text(json.dumps(entry))
            with self.assertRaises(ValidationError) as failure:
                validate_entry_package(directory, validate_categories_file(repo))
            self.assertEqual(failure.exception.code, "invalid_cover_path")

    def test_schema_paths_allow_legacy_and_canonical_but_not_unsafe_paths(self):
        schema = json.loads((ROOT / "schemas/learning-library-catalog-v1.schema.json").read_text())
        for name, filename in (("publishedTemplate", "template.json"), ("publishedCover", "cover.webp")):
            field = schema["$defs"][name]["properties"]["path"]
            self.assertEqual(field["maxLength"], 512)
            for path in (filename, f"artifacts/linked-learning/1.0.0/{filename}"):
                self.assertRegex(path, field["pattern"])
            for path in (f"../{filename}", f"https://example.com/{filename}", f"artifacts/a/../{filename}"):
                self.assertIsNone(re.fullmatch(field["pattern"], path))


if __name__ == "__main__":
    unittest.main()
