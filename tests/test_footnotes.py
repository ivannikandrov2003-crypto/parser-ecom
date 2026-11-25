import unittest

from app.footnotes import attach_footnotes, extract_footnotes


class FootnotesTest(unittest.TestCase):
    def test_backfills_a_source_note_wrapped_across_lines(self):
        source = "Автор рассказал о бренде Alpha*.\n*Оригинальное примечание\nв двух строках."
        notes = extract_footnotes(source)
        self.assertEqual(notes, [{"marker": "*", "text": "Оригинальное примечание в двух строках.", "terms": ["Alpha"]}])
        self.assertEqual(
            attach_footnotes("Alpha* представил обновление.", notes),
            ("Alpha* представил обновление.", [{"marker": "*", "text": "Оригинальное примечание в двух строках."}]),
        )

    def test_copies_referenced_html_notes_and_restores_a_missing_marker(self):
        html = b"""
            <article>
              <p>Alpha<sup><a href="#note">*</a></sup> and Beta** announced a project.</p>
              <p>** Second note.</p>
            </article>
            <aside id="note">* First note.</aside>
        """
        notes = extract_footnotes("Alpha and Beta announced a project.", html=html)
        self.assertEqual(
            attach_footnotes("BETA announced a project with Alpha*.", notes),
            (
                "BETA** announced a project with Alpha*.",
                [{"marker": "**", "text": "Second note."}, {"marker": "*", "text": "First note."}],
            ),
        )

    def test_omits_unreferenced_notes(self):
        notes = extract_footnotes("Alpha* launched a product.\n* An original source note.")
        self.assertEqual(attach_footnotes("Published today. **Bold**.", notes), ("Published today. **Bold**.", []))

    def test_omits_unverified_and_ambiguous_notes(self):
        self.assertEqual(extract_footnotes("Alpha* launched a product."), [])
        self.assertEqual(extract_footnotes("Alpha* launched.\n* First note.\n* A different note."), [])
        self.assertEqual(attach_footnotes("Alpha* launched.", []), ("Alpha* launched.", []))


if __name__ == "__main__":
    unittest.main()
