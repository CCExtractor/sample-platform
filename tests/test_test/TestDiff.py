import unittest

from mod_test.nicediff.diff import get_html_diff
from tests.base import load_file_lines
from pathlib import Path
import os

STATIC_MOCK_DIR = os.path.join(Path(__file__).parents[1], 'static_mock_files')
EXPECTED_RESULT_FILE = os.path.join(STATIC_MOCK_DIR, 'expected.txt')
OBTAINED_RESULT_FILE = os.path.join(STATIC_MOCK_DIR, 'obtained.txt')


class TestDiff(unittest.TestCase):
    def test_if_same_diff_generated(self):
        expected_sub = ['1\n', '00:00:12,340 --> 00:00:15,356\n', 'May the fourth be with you!\n']
        obtained_sub = ['1\n', '00:00:12,300 --> 00:00:15,356\n', 'May the twenty fourth be with you!\n']

        expected_diff = """
    <table>
        <tr>
            <td class="diff-table-td" style="width: 30px;">n&deg;</td>
            <td class="diff-table-td">Result</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">Expected</td>
        </tr>
    </table>
    <table>
        <tr>
            <td class="diff-table-td" style="width: 30px;">2</td>
            <td class="diff-table-td"><div class="diff-div-text"><div class="diff-same-region" id="1_diff_same_test_result_1">00:00:12,</div>300<div class="diff-same-region" id="0_diff_same_test_result_1"> --&gt; 00:00:15,356
</div></div></td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td"><div class="diff-div-text"><div class="diff-same-region" id="1_diff_same_correct_1">00:00:12,</div>340<div class="diff-same-region" id="0_diff_same_correct_1"> --&gt; 00:00:15,356
</div></div></td>
        </tr>
    </table>
    <table>
        <tr>
            <td class="diff-table-td" style="width: 30px;">3</td>
            <td class="diff-table-td"><div class="diff-div-text"><div class="diff-same-region" id="1_diff_same_test_result_2">May the</div> twenty<div class="diff-same-region" id="0_diff_same_test_result_2"> fourth be with you!
</div></div></td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td"><div class="diff-div-text"><div class="diff-same-region" id="1_diff_same_correct_2">May the</div><div class="diff-same-region" id="0_diff_same_correct_2"> fourth be with you!
</div></div></td>
        </tr>
    </table>"""

        obtained_diff = get_html_diff(expected_sub, obtained_sub)

        self.assertEqual(expected_diff, obtained_diff)

    def test_if_view_limit_respected(self):
        """
        Test that in view only first 50 diffs are sent.
        """
        expected_tr_count = 102     # 2 table rows for each diff along with 2 table rows for headings
        obtained = load_file_lines(OBTAINED_RESULT_FILE)
        expected = load_file_lines(EXPECTED_RESULT_FILE)

        obtained_diff = get_html_diff(expected, obtained, to_view=True)
        obtained_tr_count = obtained_diff.count("</tr>")

        self.assertEqual(expected_tr_count, obtained_tr_count)

    def test_if_full_diff_download(self):
        """
        Test that in download mode all diff is sent.
        """
        limit_tr_count = 102     # 2 table rows for each diff along with 2 table rows for headings
        obtained = load_file_lines(OBTAINED_RESULT_FILE)
        expected = load_file_lines(EXPECTED_RESULT_FILE)

        obtained_diff = get_html_diff(expected, obtained, to_view=False)
        obtained_tr_count = obtained_diff.count("</tr>")

        self.assertGreater(obtained_tr_count, limit_tr_count)
