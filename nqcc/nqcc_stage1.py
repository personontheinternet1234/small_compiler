#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
import argparse
import re
import subprocess
import sys


class CompileError(Exception):
    """Raised for lexing/parsing/codegen failures."""


class TokenKind(Enum):
    OPEN_BRACE = auto()
    CLOSE_BRACE = auto()
    OPEN_PAREN = auto()
    CLOSE_PAREN = auto()
    SEMICOLON = auto()
    INT_KEYWORD = auto()
    RETURN_KEYWORD = auto()
    IDENTIFIER = auto()
    INT_LITERAL = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str
    position: int


TOKEN_SPECS = [
    (TokenKind.OPEN_BRACE, re.compile(r"\{")),
    (TokenKind.CLOSE_BRACE, re.compile(r"\}")),
    (TokenKind.OPEN_PAREN, re.compile(r"\(")),
    (TokenKind.CLOSE_PAREN, re.compile(r"\)")),
    (TokenKind.SEMICOLON, re.compile(r";")),
    (TokenKind.INT_KEYWORD, re.compile(r"int\b")),
    (TokenKind.RETURN_KEYWORD, re.compile(r"return\b")),
    (TokenKind.IDENTIFIER, re.compile(r"[A-Za-z]\w*")),
    (TokenKind.INT_LITERAL, re.compile(r"[0-9]+")),
]


def lex(source: str) -> list[Token]:
    """Convert source text to tokens."""
    tokens: list[Token] = []
    i = 0

    while i < len(source):
        if source[i].isspace():
            i += 1
            continue

        for kind, pattern in TOKEN_SPECS:
            match = pattern.match(source, i)
            if match:
                value = match.group(0)
                tokens.append(Token(kind, value, i))
                i = match.end()
                break
        else:
            raise CompileError(f"Unexpected character {source[i]!r} at byte {i}")

    return tokens


@dataclass(frozen=True)
class Program:
    function: "Function"


@dataclass(frozen=True)
class Function:
    name: str
    body: "Statement"


class Statement:
    pass


@dataclass(frozen=True)
class Return(Statement):
    value: "Expression"


class Expression:
    pass


@dataclass(frozen=True)
class Constant(Expression):
    value: int


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> Token | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def consume(self, expected: TokenKind) -> Token:
        token = self.peek()
        if token is None:
            raise CompileError(f"Expected {expected.name}, but reached end of input")
        if token.kind != expected:
            raise CompileError(
                f"Expected {expected.name} at byte {token.position}, "
                f"got {token.kind.name} ({token.value!r})"
            )
        self.i += 1
        return token

    def parse_program(self) -> Program:
        function = self.parse_function()
        if self.peek() is not None:
            token = self.peek()
            raise CompileError(
                f"Unexpected extra token {token.value!r} at byte {token.position}" # type: ignore
            )
        return Program(function)

    def parse_function(self) -> Function:
        self.consume(TokenKind.INT_KEYWORD)
        name = self.consume(TokenKind.IDENTIFIER).value
        self.consume(TokenKind.OPEN_PAREN)
        self.consume(TokenKind.CLOSE_PAREN)
        self.consume(TokenKind.OPEN_BRACE)
        body = self.parse_statement()
        self.consume(TokenKind.CLOSE_BRACE)
        return Function(name=name, body=body)

    def parse_statement(self) -> Statement:
        self.consume(TokenKind.RETURN_KEYWORD)
        value = self.parse_exp()
        self.consume(TokenKind.SEMICOLON)
        return Return(value)

    def parse_exp(self) -> Expression:
        token = self.consume(TokenKind.INT_LITERAL)
        value = int(token.value)

        # Optional guard: C int return values should fit in signed 32-bit int.
        if value > 2_147_483_647:
            raise CompileError(f"Integer literal {value} exceeds signed INT_MAX")

        return Constant(value)


def parse(tokens: list[Token]) -> Program:
    return Parser(tokens).parse_program()


def _asm_symbol(name: str, platform: str) -> str:
    """macOS prefixes C symbols with _, most other Unix-like platforms do not."""
    if platform == "darwin":
        return f"_{name}"
    return name


def generate(ast: Program, *, target: str = "64", platform: str = sys.platform) -> str:
    """Generate AT&T assembly from the AST."""
    if not isinstance(ast, Program):
        raise CompileError("Code generator expected a Program AST")

    fn = ast.function
    symbol = _asm_symbol(fn.name, platform)

    if not isinstance(fn.body, Return) or not isinstance(fn.body.value, Constant):
        raise CompileError("Stage 1 only supports 'return <integer>;'")

    value = fn.body.value.value

    # For this stage, 32-bit and 64-bit assembly are intentionally the same
    # except for optional directives omitted here. Returning an int still uses %eax
    # under the common x86-64 System V ABI.
    return f""".globl {symbol}
{symbol}:
    movl    ${value}, %eax
    ret
"""


def pretty_print(ast: Program) -> str:
    fn = ast.function
    if isinstance(fn.body, Return) and isinstance(fn.body.value, Constant):
        return (
            f"FUN INT {fn.name}:\n"
            f"    params: ()\n"
            f"    body:\n"
            f"        RETURN Int<{fn.body.value.value}>"
        )
    return repr(ast)


def compile_source(
    source_path: Path,
    *,
    target: str = "64",
    keep_assembly: bool = False,
    cc: str = "gcc",
    emit_only: bool = False,
    print_ast: bool = False,
) -> Path:
    """Compile one .c file and return the generated executable path or assembly path."""
    source = source_path.read_text()
    tokens = lex(source)
    ast = parse(tokens)

    if print_ast:
        print(pretty_print(ast))

    assembly = generate(ast, target=target)
    assembly_path = source_path.with_suffix(".s")
    assembly_path.write_text(assembly)

    if emit_only:
        return assembly_path

    exe_path = source_path.with_suffix("")
    cmd = [cc]
    if target == "32":
        cmd.append("-m32")
    cmd += [str(assembly_path), "-o", str(exe_path)]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        assembly_path.unlink(missing_ok=True)
        raise CompileError(f"Compiler command not found: {cc}") from exc
    except subprocess.CalledProcessError as exc:
        assembly_path.unlink(missing_ok=True)
        raise CompileError(f"Assembler/linker command failed: {' '.join(cmd)}") from exc

    if not keep_assembly:
        assembly_path.unlink(missing_ok=True)

    return exe_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage 1 tiny C compiler")
    parser.add_argument("source_file", type=Path)
    parser.add_argument("--target", choices=["32", "64"], default="64")
    parser.add_argument("--keep-assembly", action="store_true")
    parser.add_argument("--emit-assembly", action="store_true")
    parser.add_argument("--print-ast", action="store_true")
    parser.add_argument("--cc", default="gcc", help="C compiler driver to invoke")
    args = parser.parse_args(argv)

    try:
        output = compile_source(
            args.source_file,
            target=args.target,
            keep_assembly=args.keep_assembly,
            cc=args.cc,
            emit_only=args.emit_assembly,
            print_ast=args.print_ast,
        )
        print(output)
        return 0
    except CompileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
