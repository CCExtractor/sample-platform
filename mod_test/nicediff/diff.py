import difflib
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
    """Return generated difference in HTML formatted table using smart sequence matching."""
    # variable to keep count of diff lines noted
    number_of_noted_diff_lines = 0

    html_out = """
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

    sm = difflib.SequenceMatcher(None, test_res_lines, test_correct_lines)
    
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
            break
            
        if tag == 'equal':
            continue
            
        if tag == 'replace':
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
                    break
                    
                html_out += """
    <table>"""
                
                res_idx = i1 + k
                corr_idx = j1 + k
                
                res_line = test_res_lines[res_idx] if res_idx < i2 else " "
                corr_line = test_correct_lines[corr_idx] if corr_idx < j2 else " "
                line_display = str(res_idx + 1) if res_idx < i2 else ""
                
                actual, expected = _process(res_line, corr_line, suffix_id=str(res_idx if res_idx < i2 else corr_idx))
                
                html_out += f"""
        <tr>
            <td class="diff-table-td" style="width: 30px;">{line_display}</td>
            <td class="diff-table-td">{actual}</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">{expected}</td>
        </tr>"""
                html_out += """
    </table>"""
                number_of_noted_diff_lines += 1

        elif tag == 'delete':
            for k in range(i1, i2):
                if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
                    break
                html_out += """
    <table>"""
                output, _ = _process(test_res_lines[k], " ", suffix_id=str(k))
                html_out += f"""
        <tr>
            <td class="diff-table-td" style="width: 30px;">{k + 1}</td>
            <td class="diff-table-td">{output}</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td"></td>
        </tr>"""
                html_out += """
    </table>"""
                number_of_noted_diff_lines += 1
                
        elif tag == 'insert':
            for k in range(j1, j2):
                if to_view and number_of_noted_diff_lines >= MAX_NUMBER_OF_LINES_TO_VIEW:
                    break
                html_out += """
    <table>"""
                _, output = _process(" ", test_correct_lines[k], suffix_id=str(k))
                html_out += f"""
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td"></td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">{output}</td>
        </tr>"""
                html_out += """
    </table>"""
                number_of_noted_diff_lines += 1

    return html_out
