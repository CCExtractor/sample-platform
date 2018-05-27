import unittest

from mod_test.nicediff.diff import get_html_diff

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
