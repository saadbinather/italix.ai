from italix.engines import Generation
from italix.hybrid_pr_summary import (
    HybridPRSummarizer,
    deterministic_summary,
    extract_diff_facts,
    validate_hybrid,
)


class FakeEngine:
    model_name = "fake-local"

    def __init__(self, text):
        self.text = text
        self.messages = None

    def generate(self, messages, max_tokens, temperature, adapter_path=None):
        self.messages = messages
        return Generation(self.text, self.model_name, 10, 5)


def test_extracts_supported_rename_constant_and_fallback():
    facts = extract_diff_facts("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-def old(value):
+def new(value):
+    return NAMES.get(value, NAMES[\"default\"])
-LIMIT = 8
+LIMIT = 4""")
    assert [(item.before, item.after) for item in facts.explicit_renames] == [("old", "new")]
    assert "default" in facts.fallback_values
    assert facts.added_numeric_values == ("4",)
    assert facts.removed_numeric_values == ("8",)
    assert any(item.name == "LIMIT" and item.before == "8" and item.after == "4" for item in facts.constants)


def test_unsafe_model_wording_falls_back_to_evidence_only_summary():
    engine = FakeEngine("Tests passed and this safely improves everything.")
    result = HybridPRSummarizer(engine).summarize("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-LIMIT = 8
+LIMIT = 4""")
    assert result.used_fallback is True
    assert result.validation["valid"] is True
    assert "Tests passed" not in result.summary
    assert "Set LIMIT to 4 instead of 8." in result.summary
    assert result.summary.endswith("risk level cannot be verified from the diff.")
    assert "explicit_renames" in engine.messages[1]["content"]


def test_supported_model_wording_is_bounded_by_deterministic_sections():
    engine = FakeEngine("Update LIMIT from 8 to 4.")
    result = HybridPRSummarizer(engine).summarize("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-LIMIT = 8
+LIMIT = 4""")
    assert result.used_fallback is False
    assert result.summary.startswith("## Summary\nUpdate LIMIT from 8 to 4.")
    assert "- Not run (not shown in diff)." in result.summary
    assert "Review required" in result.summary


def test_metadata_only_rename_is_reported_without_semantic_inference():
    diff = """diff --git a/docs/old.md b/docs/new.md
similarity index 100%
rename from docs/old.md
rename to docs/new.md"""
    facts = extract_diff_facts(diff)
    summary = deterministic_summary(facts)
    assert facts.file_facts[0].metadata_rename.before == "docs/old.md"
    assert "Rename file docs/old.md to docs/new.md." in summary
    assert "Semantic interpretation abstained" not in summary


def test_added_test_is_not_claimed_as_executed():
    diff = """diff --git a/tests/test_math.py b/tests/test_math.py
new file mode 100644
--- /dev/null
+++ b/tests/test_math.py
@@ -0,0 +1,2 @@
+def test_sum():
+    assert total([1, 2]) == 3"""
    facts = extract_diff_facts(diff)
    summary = deterministic_summary(facts)
    assert facts.tests_added == ("tests/test_math.py",)
    assert "Test code added in tests/test_math.py; execution not shown." in summary
    assert "tests passed" not in summary.lower()
    assert validate_hybrid(summary, facts, diff)["valid"] is True


def test_comments_do_not_become_identifiers_and_force_abstention():
    facts = extract_diff_facts("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-# retry all failures
+# retry transient failures""")
    assert facts.added_identifiers == ()
    assert facts.removed_identifiers == ()
    assert "comment-only change" in facts.abstention_reasons[0]
    assert "Semantic interpretation abstained" in deterministic_summary(facts)


def test_multiline_fallback_is_extracted_when_unambiguous():
    facts = extract_diff_facts("""diff --git a/theme.ts b/theme.ts
--- a/theme.ts
+++ b/theme.ts
@@ -1 +1,5 @@
+return THEMES.get(
+  name,
+  THEMES['accessible']
+);""")
    assert facts.fallback_values == ("accessible",)
    assert "Use explicit fallback value(s): accessible." in deterministic_summary(facts)


def test_multi_file_constants_keep_file_association():
    facts = extract_diff_facts("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-LIMIT = 1
+LIMIT = 2
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-LIMIT = 3
+LIMIT = 4""")
    summary = deterministic_summary(facts)
    assert "a.py: Set LIMIT to 2 instead of 1." in summary
    assert "b.py: Set LIMIT to 4 instead of 3." in summary


def test_deletion_only_reports_removed_code_without_behavior_claims():
    facts = extract_diff_facts("""diff --git a/legacy/cache.py b/legacy/cache.py
--- a/legacy/cache.py
+++ b/legacy/cache.py
@@ -1,2 +0,0 @@
-def clear_legacy_cache(key):
-    return legacy.delete(key)""")
    summary = deterministic_summary(facts)
    assert "Removed code identifiers: clear_legacy_cache, delete, key, legacy." in summary
    assert "faster" not in summary.lower()


def test_new_file_constants_are_file_scoped_and_factual():
    facts = extract_diff_facts("""diff --git a/config/retry.py b/config/retry.py
new file mode 100644
--- /dev/null
+++ b/config/retry.py
@@ -0,0 +1,2 @@
+MAX_RETRIES = 3
+BACKOFF_SECONDS = 2""")
    summary = deterministic_summary(facts)
    assert "Add BACKOFF_SECONDS with value 2." in summary
    assert "Add MAX_RETRIES with value 3." in summary
    assert "exponential" not in summary.lower()


def test_binary_patch_abstains_and_does_not_invent_identifiers():
    facts = extract_diff_facts("""diff --git a/logo.png b/logo.png
new file mode 100644
Binary files /dev/null and b/logo.png differ""")
    summary = deterministic_summary(facts)
    assert facts.added_identifiers == ()
    assert "binary content is not inspected" in summary


def test_helper_call_is_not_treated_as_rename():
    facts = extract_diff_facts("""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@ def public(value):
+    return select_fields(value)""")
    assert facts.explicit_renames == ()
    assert "Rename" not in deterministic_summary(facts)
