import html
import re
from typing import Any, List, Optional, Tuple, Union

index: dict = dict()  # for optimization


def zip_(ls: List[str]) -> str:
    return ''.join(ls)


# compress words and digits to one list
def compress(s: str) -> List[str]:
    return re.split(r'(\W)', s)


# equality factor
def eq(a: List[str], b: List[str], same_regions: Optional[List[List[int]]] = None,
       delta_a: int = 0, delta_b: int = 0) -> Union[List[int], List[Union[int, List[str]]]]:
    if index.get(zip_(a), dict()).get(zip_(b), None) is None:
        e = 0
        rez = []    # type: Union[int, Any, List[str]]
        best_len, a_iter, b_iter = -1, -1, -1
        find = False
        for l in range(min(len(a), len(b)), 0, -1):
            if find:
                break

            for i in range(len(a) - l + 1):
                if find:
                    break

                for j in range(len(b) - l + 1):
                    if a[i:i + l] != b[j:j + l]:
                        continue

                    find = True
                    sub_a_beg = a[0:i]
                    sub_b_beg = b[0:j]
                    _e1 = eq(sub_a_beg, sub_b_beg)[0]
                    sub_a_end = a[i + l:]
                    sub_b_end = b[j + l:]
                    _e2 = eq(sub_a_end, sub_b_end)[0]

                    if _e1 + _e2 + l > e:   # type: ignore
                        e = _e1 + _e2 + l   # type: ignore
                        best_len = l
                        a_iter = i
                        b_iter = j
                        rez = (eq(sub_a_beg, sub_b_beg)[1] + a[i: i + l] + eq(sub_a_end, sub_b_end)[1])  # type: ignore

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


# processing one line
def _process(test_result: str, correct: str, suffix_id: str) -> Tuple[str, str]:
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

    html_test = ''
    idx = 0
    for event in events_test:
        while idx < event[0]:   # type: ignore
            html_test += tr_compr[idx]
            idx += 1
        if event[1] == 'OPEN':
            _id = "{region}_diff_same_test_result_{suffix}".format(region=event[2], suffix=suffix_id)
            cl = '<div class="diff-same-region" id="{id}">'.format(id=_id)
            html_test += cl
        else:
            html_test += '</div>'
    html_test += ''.join(tr_compr[idx:])

    html_correct = ''
    idx = 0
    for event in events_correct:
        while idx < event[0]:   # type: ignore
            html_correct += cr_compr[idx]
            idx += 1
        if event[1] == 'OPEN':
            _id = "{region}_diff_same_correct_{suffix}".format(region=event[2], suffix=suffix_id)
            cl = '<div class="diff-same-region" id="{id}">'.format(id=_id)
            html_correct += cl
        else:
            html_correct += '</div>'
    html_correct += ''.join(cr_compr[idx:])
    return '<div class="diff-div-text">' + html_test + '</div>', '<div class="diff-div-text">' + html_correct + '</div>'


# return generated difference in HTML formatted table
def get_html_diff(test_correct_lines: List[str], test_res_lines: List[str]) -> str:
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
        if test_correct_lines[line] == test_res_lines[line]:
            continue
        html += """
    <table>"""
        actual, expected = _process(test_res_lines[line], test_correct_lines[line], suffix_id=str(line))

        html += """
        <tr>
            <td class="diff-table-td" style="width: 30px;">{line_id}</td>
            <td class="diff-table-td">{a}</td>
        </tr>
        <tr>
            <td class="diff-table-td" style="width: 30px;"></td>
            <td class="diff-table-td">{b}</td>
        </tr>""".format(line_id=line + 1, a=actual, b=expected)
        html += """
    </table>"""

    # processing remaining lines
    for line in range(use, till):
        html += """
    <table>"""

        if till == res_len:
            output, _ = _process(test_res_lines[line], " ", suffix_id=str(line))
            html += """
            <tr>
                <td class="diff-table-td" style="width: 30px;">{line_id}</td>
                <td class="diff-table-td">{a}</td>
            </tr>
            <tr>
                <td class="diff-table-td" style="width: 30px;"></td>
                <td class="diff-table-td"></td>
            </tr>
            """.format(line_id=line + 1, a=output)
        else:
            _, output = _process(" ", test_correct_lines[line], suffix_id=str(line))
            html += """
            <tr>
                <td class="diff-table-td" style="width: 30px;">{line_id}</td>
                <td class="diff-table-td"></td>
            </tr>
            <tr>
                <td class="diff-table-td" style="width: 30px;"></td>
                <td class="diff-table-td">{b}</td>
            </tr>
            """.format(line_id=line + 1, b=output)

        html += """
    <table>"""

    return html
