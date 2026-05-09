import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expr_parser import parse, evaluate


def match(expr: str, text: str) -> bool:
    return evaluate(parse(expr), text)


class TestAnd(unittest.TestCase):
    def test_both_present(self):
        self.assertTrue(match("python AND flask", "flask python tutorial"))

    def test_one_missing(self):
        self.assertFalse(match("python AND flask", "python tutorial"))

    def test_neither(self):
        self.assertFalse(match("python AND flask", "java spring"))


class TestOr(unittest.TestCase):
    def test_first(self):
        self.assertTrue(match("python OR java", "python is great"))

    def test_second(self):
        self.assertTrue(match("python OR java", "java is great"))

    def test_neither(self):
        self.assertFalse(match("python OR java", "ruby rails"))


class TestNot(unittest.TestCase):
    def test_absent(self):
        self.assertTrue(match("NOT вакансия", "python tutorial"))

    def test_present(self):
        self.assertFalse(match("NOT вакансия", "вакансия python"))


class TestCombinations(unittest.TestCase):
    def test_and_not_pass(self):
        self.assertTrue(match("python AND NOT вакансия", "вышел python 3.13"))

    def test_and_not_fail(self):
        self.assertFalse(match("python AND NOT вакансия", "вакансия python разработчик"))

    def test_or_and_pass(self):
        self.assertTrue(match("(flask OR django) AND python", "python flask app"))

    def test_or_and_fail(self):
        self.assertFalse(match("(flask OR django) AND python", "java django app"))

    def test_nested_pass(self):
        self.assertTrue(match("(a OR b) AND NOT c", "a здесь"))

    def test_nested_fail_not(self):
        self.assertFalse(match("(a OR b) AND NOT c", "a и c здесь"))

    def test_nested_fail_or(self):
        self.assertFalse(match("(a OR b) AND NOT c", "только c"))

    def test_double_not_pass(self):
        self.assertTrue(match("NOT NOT python", "python есть"))

    def test_double_not_fail(self):
        self.assertFalse(match("NOT NOT python", "java только"))

    def test_complex(self):
        expr = "python AND (flask OR django) AND NOT вакансия AND NOT реклама"
        self.assertTrue(match(expr, "туториал flask python"))
        self.assertFalse(match(expr, "вакансия python flask разработчик"))
        self.assertFalse(match(expr, "реклама django python курс"))


class TestQuotedPhrases(unittest.TestCase):
    def test_match(self):
        self.assertTrue(match('"новый релиз"', "вышел новый релиз python"))

    def test_no_match(self):
        self.assertFalse(match('"новый релиз"', "просто новый python"))

    def test_with_and_pass(self):
        self.assertTrue(match('"новый релиз" AND python', "вышел новый релиз python"))

    def test_with_and_fail(self):
        self.assertFalse(match('"новый релиз" AND python', "вышел новый релиз java"))


class TestCaseInsensitivity(unittest.TestCase):
    def test_term_upper(self):
        self.assertTrue(match("Python", "python tutorial"))

    def test_term_lower(self):
        self.assertTrue(match("python", "Python Tutorial"))

    def test_quoted(self):
        self.assertTrue(match('"Hello World"', "hello world here"))


class TestSingleTerm(unittest.TestCase):
    def test_match(self):
        self.assertTrue(match("python", "python"))

    def test_no_match(self):
        self.assertFalse(match("python", "java"))


class TestInvalidExpressions(unittest.TestCase):
    def _assert_syntax_error(self, expr: str):
        with self.assertRaises(SyntaxError):
            parse(expr)

    def test_empty(self):
        self._assert_syntax_error("")

    def test_bare_and(self):
        self._assert_syntax_error("AND")

    def test_dangling_operator(self):
        self._assert_syntax_error("python AND")

    def test_unclosed_paren(self):
        self._assert_syntax_error("(python AND flask")

    def test_unclosed_quote(self):
        self._assert_syntax_error('"незакрытая')

    def test_implicit_and(self):
        # Bare sequence without explicit operator is invalid
        self._assert_syntax_error("python flask")


if __name__ == "__main__":
    unittest.main()
