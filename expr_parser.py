from __future__ import annotations
from dataclasses import dataclass
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
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 1
            if j >= len(text):
                raise SyntaxError("Незакрытая кавычка в выражении")
            tokens.append(_Token(_TT.TERM, text[i + 1 : j]))
            i = j + 1
        else:
            j = i
            while j < len(text) and not text[j].isspace() and text[j] not in '()"':
                j += 1
            word = text[i:j]
            if word == "AND":
                tokens.append(_Token(_TT.AND))
            elif word == "OR":
                tokens.append(_Token(_TT.OR))
            elif word == "NOT":
                tokens.append(_Token(_TT.NOT))
            elif word:
                tokens.append(_Token(_TT.TERM, word))
            i = j
    tokens.append(_Token(_TT.EOF))
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class TermNode:
    value: str

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
            return TermNode(tok.value)
        raise SyntaxError(
            f"Ожидалось слово или '(', получено "
            + (f"{tok.value!r}" if tok.value else tok.type.name)
        )


def parse(expression: str) -> Node:
    """Parse a boolean filter expression into an AST. Raises SyntaxError on invalid input."""
    return _Parser(_tokenize(expression)).parse()


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate(node: Node, text: str) -> bool:
    """Return True if *text* satisfies the boolean expression represented by *node*."""
    return _eval(node, text.lower())


def _eval(node: Node, text_lower: str) -> bool:
    if isinstance(node, TermNode):
        return node.value.lower() in text_lower
    if isinstance(node, NotNode):
        return not _eval(node.operand, text_lower)
    if isinstance(node, AndNode):
        return _eval(node.left, text_lower) and _eval(node.right, text_lower)
    if isinstance(node, OrNode):
        return _eval(node.left, text_lower) or _eval(node.right, text_lower)
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
