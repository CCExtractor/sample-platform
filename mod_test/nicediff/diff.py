import html
import re
from typing import Any, List, Optional, Tuple, Union

# number of lines to show in view mode
MAX_NUMBER_OF_LINES_TO_VIEW = 50

index: dict = dict()  # for optimization


def zip_(ls: List[str]) -> str:
    """Add an alias for strings joining."""
    return ''.join(ls)


def compress(s: str) -> List[str]:
    """Compress words and digits to one list."""
    return re.split(r'(\W)', s)


def eq(a: List[str], b: List[str], same_regions: Optional[List[List[int]]] = None,
       delta_a: int = 0, delta_b: int = 0) -> Union[List[int], List[Union[int, List[str]]]]:
    """Implement equality factor."""
    if index.get(zip_(a), dict()).get(zip_(b), None) is None:
        e = 0
        rez = []    # type: Union[int, Any, List[str]]
        best_len, a_iter, b_iter = -1, -1, -1
        find = False
        for line in range(min(len(a), len(b)), 0, -1):
            if find:
                break

            for i in range(len(a) - line + 1):
                if find:
                    break

                for j in range(len(b) - line + 1):
                    if a[i:i + line] != b[j:j + line]:
                        continue

                    find = True
                    sub_a_beg = a[0:i]
                    sub_b_beg = b[0:j]
                    _e1 = eq(sub_a_beg, sub_b_beg)[0]
                    sub_a_end = a[i + line:]
                    sub_b_end = b[j + line:]
                    _e2 = eq(sub_a_end, sub_b_end)[0]

                    if _e1 + _e2 + line > e:   # type: ignore
                        e = _e1 + _e2 + line   # type: ignore
                        best_len = line
                        a_iter = i
                        b_iter = j
                        rez = (eq(sub_a_beg, sub_b_beg)[1] + a[i: i + line] + eq(sub_a_end,  # type: ignore
                                                                                 sub_b_end)[1])

        index[zip_(a)] = index.get(zip_(a), dict())
        index[zip_(a)][zip_(b)] = [e, rez, a_iter, b_iter, best_len]

    if same_regions is not None and index[zip_(a)][zip_(b)][0] > 1:
        a_iter, b_iter, best_len = index[zip_(a)][zip_(b)][2:]
        # print(delta)
        same_regions.append([
            a_iter + delta_a, a_iter + best_len + delta_a,
            b_iter + delta_b, b_iter + best_len + delta_b
        ])
        sub_a_beg = a[0:a_iter]
        sub_b_beg = b[0:b_iter]
        sub_a_end = a[a_iter + best_len:]
        sub_b_end = b[b_iter + best_len:]

        eq(sub_a_beg, sub_b_beg, same_regions, delta_a, delta_b)
        eq(sub_a_end, sub_b_end, same_regions, delta_a + a_iter + best_len, delta_b + b_iter + best_len)

    return index[zip_(a)][zip_(b)]


def _process(test_result: str, correct: str, suffix_id: str) -> Tuple[str, str]:
    """Process one line."""
    test_result = html.escape(test_result)
    correct = html.escape(correct)
    tr_compr = compress(test_result)
    cr_compr = compress(correct)
    regions = []    # type: List[List[int]]
    eq(tr_compr, cr_compr, same_regions=regions)

    events_test = []    # type: List[List[object]]
    events_correct = []

    for reg_id in range(len(regions)):
        reg = regions[reg_id]
        events_test.append([reg[0], 'OPEN', reg_id])
        events_test.append([reg[1], 'CLOSE', reg_id])

        events_correct.append([reg[2], 'OPEN', reg_id])
        events_correct.append([reg[3], 'CLOSE', reg_id])

    events_test.sort()
    events_correct.sort()

    html_test = create_diff_entries(suffix_id, 'test_result', events_test, tr_compr)
    html_correct = create_diff_entries(suffix_id, 'correct', events_correct, cr_compr)

    return f'<div class="diff-div-text">{html_test}</div>', f'<div class="diff-div-text">{html_correct}</div>'


def create_diff_entries(suffix_id: str, id_name: str, events: List[List[object]], compressed_data: List[str]) -> str:
    """Create the diff entries for the correct or wrong side."""
    result = ''
    idx = 0
    for event in events:
        while idx < event[0]:  # type: ignore
            result += compressed_data[idx]
            idx += 1
        if event[1] == 'OPEN':
            cl = f'<div class="diff-same-region" id="{event[2]}_diff_same_{id_name}_{suffix_id}">'
            result += cl
        else:
            result += '</div>'
    result += ''.join(compressed_data[idx:])
    return result


def get_html_diff(test_correct_lines: List[str], test_res_lines: List[str], to_view: bool = True) -> str:
    """Return generated difference in HTML formatted table."""
    # variable to keep count of diff lines noted
    number_of_noted_diff_lines = 0

    html = """
    <table>
        <tr>
            <td class="diff-table-td" style="width: 30px;">n&deg;</td>
            <td class="diff-table-td">Result</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">Expected</td>
        </tr>
    </table>"""

    res_len = len(test_res_lines)
    correct_len = len(test_correct_lines)

    if res_len <= correct_len:
        use = res_len
        till = correct_len

    else:
        use = correct_len
        till = res_len

    for line in range(use):
        if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
            break

        if test_correct_lines[line] == test_res_lines[line]:
            continue
        html += """
    <table>"""
        actual, expected = _process(test_res_lines[line], test_correct_lines[line], suffix_id=str(line))

        html += f"""
        <tr>
            <td class="diff-table-td" style="width: 30px;">{line + 1}</td>
            <td class="diff-table-td">{actual}</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">{expected}</td>
        </tr>"""
        html += """
    </table>"""

        # increase noted diff line by one
        number_of_noted_diff_lines += 1

    # processing remaining lines
    for line in range(use, till):

        # stop at 50 lines if test-data for viewing
        if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
            break

        html += """
    <table>"""

        if till == res_len:
            output, _ = _process(test_res_lines[line], " ", suffix_id=str(line))
            html += f"""
            <tr>
                <td class="diff-table-td" style="width: 30px;">{line + 1}</td>
                <td class="diff-table-td">{output}</td>
            </tr>
            <tr>
                <td class="diff-table-td" style="width: 30px;"></td>
                <td class="diff-table-td"></td>
            </tr>
            """
        else:
            _, output = _process(" ", test_correct_lines[line], suffix_id=str(line))
            html += f"""
            <tr>
                <td class="diff-table-td" style="width: 30px;">{line + 1}</td>
                <td class="diff-table-td"></td>
            </tr>
            <tr>
                <td class="diff-table-td" style="width: 30px;"></td>
                <td class="diff-table-td">{output}</td>
            </tr>
            """

        html += """
    <table>"""

        # increase noted diff line by one
        number_of_noted_diff_lines += 1

    return html
