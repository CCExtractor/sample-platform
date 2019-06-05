from markdown2 import markdown

from tests.base import BaseTestCase


class TestMarkdown(BaseTestCase):

    def test_heading(self):
        """
        test conversion of markdown heading to html
        """
        mkdown_test1 = "# I'm a heading"
        expected_test1 = "<h1>I'm a heading</h1>\n"

        mkdown_test2 = "## I'm a heading"
        expected_test2 = "<h2>I'm a heading</h2>\n"

        html_test1 = markdown(mkdown_test1)
        html_test2 = markdown(mkdown_test2)

        assert expected_test1 == html_test1, "wrong conversion for heading 1"
        assert expected_test2 == html_test2, "wrong conversion for heading 2"

    def test_strong_text(self):
        """
        test conversion of markdown bold to html
        """
        mkdown_test1 = "**I'm a strong text**"
        expected_test1 = "<p><strong>I'm a strong text</strong></p>\n"

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for bold text"

    def test_italics_text(self):
        """
        test conversion of markdown italics to html
        """
        mkdown_test1 = "*I'm a emphasized text*"
        expected_test1 = "<p><em>I'm a emphasized text</em></p>\n"

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for italics text"

    def test_link_text(self):
        """
        test conversion of markdown hyperlinks to html
        """
        mkdown_test1 = "[i'm a hyperlink](www.example.com)"
        expected_test1 = """<p><a href="www.example.com">i'm a hyperlink</a></p>\n"""

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for hyperlink text"

    def test_list_text(self):
        """
        test conversion of markdown list to html
        """
        mkdown_test1 = "- i'm a list text"
        expected_test1 = "<ul>\n<li>i'm a list text</li>\n</ul>\n"

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for list text"

    def test_code_text(self):
        """
        test conversion of markdown code text to html
        """
        mkdown_test1 = "`i'm a code`"
        expected_test1 = "<p><code>i'm a code</code></p>\n"

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for code text"

    def test_quote_text(self):
        """
        test conversion of markdown quote text to html
        """
        mkdown_test1 = "> i'm a quote"
        expected_test1 = "<blockquote>\n  <p>i'm a quote</p>\n</blockquote>\n"

        html_test1 = markdown(mkdown_test1)

        assert expected_test1 == html_test1, "wrong conversion for quote text"

    def test_extra_link_new_tab(self):
        """
        test addition of target="_blank" attribute to anchor tags
        """
        mkdown_test1 = "[I'll open in new tab](www.example.com)"
        expected_test1 = """<p><a target="_blank" href="www.example.com">I'll open in new tab</a></p>\n"""

        html_test1 = markdown(mkdown_test1, extras=["target-blank-links"])

        assert expected_test1 == html_test1, "no target attribute added to anchor tag"

    def test_extra_task_list(self):
        """
        test addition of target="_blank" attribute to anchor tags
        """
        mkdown_test1 = "- [x] I'm a task"
        expected_test1 = ("""<ul>\n<li><input type="checkbox" class="task-list-item-checkbox" checked disabled> """
                          """I'm a task</li>\n</ul>\n""")

        html_test1 = markdown(mkdown_test1, extras=["task_list"])
        print(html_test1)

        assert expected_test1 == html_test1, "no target attribute added to anchor tag"

    def test_extra_code_friendliness(self):
        """
        test no conversion of markdown code style bold and italics to html
        """
        mkdown_test1 = "__I'm not a strong text__"
        expected_test1 = "<p>__I'm not a strong text__</p>\n"

        mkdown_test2 = "_I'm not an italics text_"
        expected_test2 = "<p>_I'm not an italics text_</p>\n"

        html_test1 = markdown(mkdown_test1, extras=["code-friendly"])
        html_test2 = markdown(mkdown_test2, extras=["code-friendly"])

        assert expected_test1 == html_test1, "wrong conversion for code-style bold text"
        assert expected_test2 == html_test2, "wrong conversion for code-style italics text"
