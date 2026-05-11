from __future__ import annotations
import re as _re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

class _TT(Enum):
    AND = auto()
    OR = auto()
    NOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    TERM = auto()
    EOF = auto()


@dataclass
class _Token:
    type: _TT
    value: str = ""
    mode: str = "substr"  # "substr" | "glob" | "regex"


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append(_Token(_TT.LPAREN))
            i += 1
        elif ch == ")":
            tokens.append(_Token(_TT.RPAREN))
            i += 1
        elif ch == '"':
            # Quoted phrase → exact substring match
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 1
            if j >= len(text):
                raise SyntaxError("Незакрытая кавычка в выражении")
            tokens.append(_Token(_TT.TERM, text[i + 1 : j], "substr"))
            i = j + 1
        elif ch == "/":
            # Regex pattern: /pattern/
            j = i + 1
            while j < len(text) and text[j] != "/":
                if text[j] == "\\" and j + 1 < len(text):
                    j += 2  # skip escaped char
                else:
                    j += 1
            if j >= len(text):
                raise SyntaxError("Незакрытый regex-паттерн (нет закрывающего '/')")
            pattern = text[i + 1 : j]
            # Validate regex at parse time
            try:
                _re.compile(pattern)
            except _re.error as e:
                raise SyntaxError(f"Некорректный regex '{pattern}': {e}") from e
            tokens.append(_Token(_TT.TERM, pattern, "regex"))
            i = j + 1
        else:
            # Plain word, glob (contains * or ?), or @username (author filter)
            j = i
            while j < len(text) and not text[j].isspace() and text[j] not in '()"/' :
                j += 1
            word = text[i:j]
            if word == "AND":
                tokens.append(_Token(_TT.AND))
            elif word == "OR":
                tokens.append(_Token(_TT.OR))
            elif word == "NOT":
                tokens.append(_Token(_TT.NOT))
            elif word.startswith("@"):
                if len(word) < 2:
                    raise SyntaxError("Пустой @username в выражении")
                tokens.append(_Token(_TT.TERM, word[1:], "author"))
            elif word:
                mode = "glob" if ("*" in word or "?" in word) else "substr"
                tokens.append(_Token(_TT.TERM, word, mode))
            i = j
    tokens.append(_Token(_TT.EOF))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class TermNode:
    value: str
    mode: str = "substr"  # "substr" | "glob" | "regex" | "author"

@dataclass
class NotNode:
    operand: "Node"

@dataclass
class AndNode:
    left: "Node"
    right: "Node"

@dataclass
class OrNode:
    left: "Node"
    right: "Node"

Node = Union[TermNode, NotNode, AndNode, OrNode]


# ---------------------------------------------------------------------------
# Parser (recursive descent)
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _consume(self, expected: _TT | None = None) -> _Token:
        tok = self._tokens[self._pos]
        if expected is not None and tok.type != expected:
            raise SyntaxError(
                f"Ожидалось {expected.name}, получено {tok.type.name}"
                + (f" ({tok.value!r})" if tok.value else "")
            )
        self._pos += 1
        return tok

    def parse(self) -> Node:
        if self._peek().type == _TT.EOF:
            raise SyntaxError("Пустое выражение")
        node = self._parse_or()
        if self._peek().type != _TT.EOF:
            raise SyntaxError(f"Неожиданный токен: {self._peek().value!r}")
        return node

    def _parse_or(self) -> Node:
        left = self._parse_and()
        while self._peek().type == _TT.OR:
            self._consume(_TT.OR)
            right = self._parse_and()
            left = OrNode(left, right)
        return left

    def _parse_and(self) -> Node:
        left = self._parse_not()
        while self._peek().type == _TT.AND:
            self._consume(_TT.AND)
            right = self._parse_not()
            left = AndNode(left, right)
        return left

    def _parse_not(self) -> Node:
        if self._peek().type == _TT.NOT:
            self._consume(_TT.NOT)
            return NotNode(self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> Node:
        tok = self._peek()
        if tok.type == _TT.LPAREN:
            self._consume(_TT.LPAREN)
            node = self._parse_or()
            self._consume(_TT.RPAREN)
            return node
        if tok.type == _TT.TERM:
            self._consume(_TT.TERM)
            return TermNode(tok.value, tok.mode)
        raise SyntaxError(
            f"Ожидалось слово, паттерн или '(', получено "
            + (f"{tok.value!r}" if tok.value else tok.type.name)
        )


def parse(expression: str) -> Node:
    """Parse a boolean filter expression into an AST. Raises SyntaxError on invalid input."""
    return _Parser(_tokenize(expression)).parse()


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate(node: Node, text: str, author: str = "") -> bool:
    """Return True if the message satisfies the expression.

    Args:
        node:   parsed AST
        text:   raw message text
        author: sender username (without @) or user ID as string; empty if unknown
    """
    return _eval(node, text.lower(), author.lower())


def _match_term(node: TermNode, text_lower: str, author_lower: str) -> bool:
    if node.mode == "author":
        return node.value.lower() == author_lower
    if node.mode == "regex":
        try:
            return bool(_re.search(node.value, text_lower, _re.IGNORECASE))
        except _re.error:
            return False
    if node.mode == "glob":
        pattern = _re.escape(node.value).replace(r"\*", ".*").replace(r"\?", ".")
        return bool(_re.search(pattern, text_lower, _re.IGNORECASE))
    return node.value.lower() in text_lower


def _eval(node: Node, text_lower: str, author_lower: str = "") -> bool:
    if isinstance(node, TermNode):
        return _match_term(node, text_lower, author_lower)
    if isinstance(node, NotNode):
        return not _eval(node.operand, text_lower, author_lower)
    if isinstance(node, AndNode):
        return _eval(node.left, text_lower, author_lower) and _eval(node.right, text_lower, author_lower)
    if isinstance(node, OrNode):
        return _eval(node.left, text_lower, author_lower) or _eval(node.right, text_lower, author_lower)
    raise TypeError(f"Unknown AST node type: {type(node)}")


# ---------------------------------------------------------------------------
# AST cache (filter_id → Node)
# ---------------------------------------------------------------------------

_cache: dict[int, Node] = {}


def get_ast(filter_id: int, expression: str) -> Node:
    if filter_id not in _cache:
        _cache[filter_id] = parse(expression)
    return _cache[filter_id]


def invalidate(filter_id: int) -> None:
    _cache.pop(filter_id, None)
