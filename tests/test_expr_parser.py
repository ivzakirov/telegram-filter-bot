import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from expr_parser import parse, evaluate


def match(expr: str, text: str) -> bool:
    return evaluate(parse(expr), text)


# ---------------------------------------------------------------------------
# AND / OR / NOT
# ---------------------------------------------------------------------------

class TestAnd(unittest.TestCase):
    def test_both_present(self):    self.assertTrue(match("python AND flask", "flask python tutorial"))
    def test_one_missing(self):     self.assertFalse(match("python AND flask", "python tutorial"))
    def test_neither(self):         self.assertFalse(match("python AND flask", "java spring"))

class TestOr(unittest.TestCase):
    def test_first(self):   self.assertTrue(match("python OR java", "python is great"))
    def test_second(self):  self.assertTrue(match("python OR java", "java is great"))
    def test_neither(self): self.assertFalse(match("python OR java", "ruby rails"))

class TestNot(unittest.TestCase):
    def test_absent(self):  self.assertTrue(match("NOT vacancy", "python tutorial"))
    def test_present(self): self.assertFalse(match("NOT vacancy", "vacancy python"))

class TestCombinations(unittest.TestCase):
    def test_and_not_pass(self):    self.assertTrue(match("python AND NOT vacancy", "python 3.13 released"))
    def test_and_not_fail(self):    self.assertFalse(match("python AND NOT vacancy", "vacancy python developer"))
    def test_or_and_pass(self):     self.assertTrue(match("(flask OR django) AND python", "python flask app"))
    def test_or_and_fail(self):     self.assertFalse(match("(flask OR django) AND python", "java django app"))
    def test_nested_pass(self):     self.assertTrue(match("(a OR b) AND NOT c", "a here"))
    def test_nested_fail_not(self): self.assertFalse(match("(a OR b) AND NOT c", "a and c here"))
    def test_double_not_pass(self): self.assertTrue(match("NOT NOT python", "python present"))
    def test_double_not_fail(self): self.assertFalse(match("NOT NOT python", "java only"))


# ---------------------------------------------------------------------------
# Quoted phrases
# ---------------------------------------------------------------------------

class TestQuotedPhrases(unittest.TestCase):
    def test_match(self):       self.assertTrue(match('"new release"', "new release of python"))
    def test_no_match(self):    self.assertFalse(match('"new release"', "just new python"))
    def test_with_and(self):    self.assertTrue(match('"new release" AND python', "new release of python"))


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------

class TestCaseInsensitivity(unittest.TestCase):
    def test_term_upper(self):  self.assertTrue(match("Python", "python tutorial"))
    def test_term_lower(self):  self.assertTrue(match("python", "Python Tutorial"))
    def test_quoted(self):      self.assertTrue(match('"Hello World"', "hello world here"))


# ---------------------------------------------------------------------------
# Glob wildcards
# ---------------------------------------------------------------------------

class TestGlob(unittest.TestCase):
    def test_star_suffix_match(self):
        self.assertTrue(match("python*", "python3 released"))

    def test_star_suffix_bare_word(self):
        self.assertTrue(match("python*", "python"))

    def test_star_suffix_no_match(self):
        self.assertFalse(match("python*", "java spring"))

    def test_star_prefix_match(self):
        self.assertTrue(match("*spam*", "this is spam buy now"))

    def test_star_prefix_no_match(self):
        self.assertFalse(match("*spam*", "interesting post"))

    def test_question_mark(self):
        self.assertTrue(match("bike?", "buy bikes"))

    def test_question_mark_no_match(self):
        self.assertFalse(match("bike?", "python"))

    def test_glob_in_expression(self):
        self.assertTrue(match("python* AND NOT vacancy*", "python3.13 released"))
        self.assertFalse(match("python* AND NOT vacancy*", "vacancy python developer"))

    def test_glob_case_insensitive(self):
        self.assertTrue(match("Python*", "python3"))


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

class TestRegex(unittest.TestCase):
    def test_simple_match(self):
        self.assertTrue(match("/python/", "this is a python tutorial"))

    def test_simple_no_match(self):
        self.assertFalse(match("/python/", "java spring"))

    def test_alternation(self):
        self.assertTrue(match("/py(thon|3)/", "py3 released"))
        self.assertTrue(match("/py(thon|3)/", "python released"))
        self.assertFalse(match("/py(thon|3)/", "java released"))

    def test_character_class(self):
        self.assertTrue(match("/bike[sd]/", "buy bikes"))
        self.assertFalse(match("/bike[sd]/", "just bike"))

    def test_regex_in_expression(self):
        self.assertTrue(match("/ad[sz]?/ OR /spam/", "this is ads"))
        self.assertTrue(match("/ad[sz]?/ OR /spam/", "this is spam"))
        self.assertFalse(match("/ad[sz]?/ OR /spam/", "interesting post"))

    def test_regex_case_insensitive(self):
        self.assertTrue(match("/Python/", "python tutorial"))

    def test_invalid_regex_raises(self):
        with self.assertRaises(SyntaxError):
            parse("/[invalid/")


# ---------------------------------------------------------------------------
# Single term edge cases
# ---------------------------------------------------------------------------

class TestSingleTerm(unittest.TestCase):
    def test_match(self):       self.assertTrue(match("python", "python"))
    def test_no_match(self):    self.assertFalse(match("python", "java"))


# ---------------------------------------------------------------------------
# Invalid expressions
# ---------------------------------------------------------------------------

class TestInvalidExpressions(unittest.TestCase):
    def _err(self, expr):
        with self.assertRaises(SyntaxError):
            parse(expr)

    def test_empty(self):           self._err("")
    def test_bare_and(self):        self._err("AND")
    def test_dangling_operator(self): self._err("python AND")
    def test_unclosed_paren(self):  self._err("(python AND flask")
    def test_unclosed_quote(self):  self._err('"unclosed')
    def test_unclosed_regex(self):  self._err("/unclosed")
    def test_implicit_and(self):    self._err("python flask")


if __name__ == "__main__":
    unittest.main()
