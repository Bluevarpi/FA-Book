#!/usr/bin/env python3
"""Token-aware LaTeX lint for the functional-analysis book notation and source-style contract."""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

VERBATIM_ENVS = {"verbatim", "Verbatim", "lstlisting", "minted"}
SCAN_SUFFIXES = {".tex", ".sty", ".cls"}
DISPLAY_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*",
}
DISPLAY_OPEN_LINE_RE = re.compile(
    r"^\s*(?:\\\[|\\begin\{(?:equation\*?|align\*?|gather\*?|multline\*?)\})"
)
NESTED_DISPLAY_ENVS = {"aligned", "gathered", "split"}
MACHINE_ARG_COMMANDS = {
    "label", "ref", "autoref", "eqref", "pageref", "cite", "parencite",
    "textcite", "url", "path", "input", "include", "includegraphics",
    "addbibresource", "bibliography", "index", "texttt",
    "ctexset", "hypersetup", "tcbset", "tikzset", "captionsetup", "setlist",
}

HARD_WORD_RULES = {
    "ldots": ("L001", r"noncanonical control word \\ldots"),
    "epsilon": ("L002", r"noncanonical control word \\epsilon"),
    "phi": ("L003", r"noncanonical control word \\phi"),
    "le": ("L004", r"noncanonical <= control word"),
    "leq": ("L004", r"noncanonical <= control word"),
    "leqq": ("L004", r"noncanonical <= control word"),
    "ge": ("L005", r"noncanonical >= control word"),
    "geq": ("L005", r"noncanonical >= control word"),
    "geqq": ("L005", r"noncanonical >= control word"),
    "exp": ("L006", r"noncanonical control word \\exp"),
    "qed": ("L010", r"forbidden automatic/procedural QED control word"),
    "qedhere": ("L010", r"forbidden automatic/procedural QED control word"),
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class Finding:
    rule: str
    path: Path
    line: int
    message: str
    severity: str = "HARD"


@dataclass(frozen=True)
class InlinePair:
    open_pos: int
    content_start: int
    content_end: int
    close_end: int


def mask_region(chars: list[str], start: int, end: int) -> None:
    for i in range(start, min(end, len(chars))):
        if chars[i] != "\n":
            chars[i] = " "


def is_escaped_percent(text: str, pos: int) -> bool:
    n = 0
    j = pos - 1
    while j >= 0 and text[j] == "\\":
        n += 1
        j -= 1
    return n % 2 == 1


def mask_noncode(text: str) -> str:
    """Mask comments, verbatim-like environments and inline verbatim, preserving length/newlines."""
    chars = list(text)
    n = len(text)
    i = 0
    block_env: str | None = None
    while i < n:
        if block_env is not None:
            needle = rf"\end{{{block_env}}}"
            j = text.find(needle, i)
            if j < 0:
                mask_region(chars, i, n)
                break
            mask_region(chars, i, j + len(needle))
            i = j + len(needle)
            block_env = None
            continue

        if text[i] == "%" and not is_escaped_percent(text, i):
            j = text.find("\n", i)
            if j < 0:
                j = n
            mask_region(chars, i, j)
            i = j
            continue

        matched_env = None
        for env in VERBATIM_ENVS:
            needle = rf"\begin{{{env}}}"
            if text.startswith(needle, i):
                matched_env = env
                mask_region(chars, i, i + len(needle))
                i += len(needle)
                block_env = env
                break
        if matched_env is not None:
            continue

        inline_cmd = None
        for cmd in (r"\verb*", r"\verb", r"\Verb", r"\lstinline"):
            if text.startswith(cmd, i):
                inline_cmd = cmd
                break
        if inline_cmd is not None:
            dpos = i + len(inline_cmd)
            if dpos < n and text[dpos] not in "\r\n \t":
                delim = text[dpos]
                end = text.find(delim, dpos + 1)
                if end < 0:
                    end = text.find("\n", dpos + 1)
                    if end < 0:
                        end = n - 1
                mask_region(chars, i, end + 1)
                i = end + 1
                continue

        i += 1
    return "".join(chars)


def iter_tokens(text: str) -> Iterator[Token]:
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "\\":
            i += 1
            continue
        start = i
        i += 1
        if i >= n:
            yield Token("symbol", "", start, i)
            continue
        if text[i].isalpha() or text[i] == "@":
            j = i + 1
            while j < n and (text[j].isalpha() or text[j] == "@"):
                j += 1
            yield Token("word", text[i:j], start, j)
            i = j
        else:
            yield Token("symbol", text[i], start, i + 1)
            i += 1


def line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(i + 1 for i, ch in enumerate(text) if ch == "\n")
    return starts


def line_number(starts: list[int], pos: int) -> int:
    return bisect.bisect_right(starts, pos)


def current_math_kind(stack: list[tuple[str, str | None, int, int]]) -> str:
    if not stack:
        return "TEXT"
    return stack[-1][0]


def parse_math_regions(text: str) -> tuple[list[str], list[InlinePair], list[int]]:
    """Return per-character TEXT/INLINE_MATH/DISPLAY_MATH map, inline pairs, unmatched inline openers."""
    region = ["TEXT"] * len(text)
    stack: list[tuple[str, str | None, int, int]] = []
    inline_pairs: list[InlinePair] = []
    unmatched_inline: list[int] = []
    i = 0
    n = len(text)

    def paint(a: int, b: int, kind: str) -> None:
        for k in range(a, min(b, n)):
            region[k] = kind

    while i < n:
        kind = current_math_kind(stack)

        if text.startswith(r"\(", i):
            if kind == "TEXT":
                paint(i, i + 2, "INLINE_MATH")
                stack.append(("INLINE_MATH", None, i, i + 2))
            else:
                paint(i, i + 2, kind)
            i += 2
            continue

        if text.startswith(r"\)", i):
            if stack and stack[-1][0] == "INLINE_MATH":
                frame = stack.pop()
                paint(i, i + 2, "INLINE_MATH")
                inline_pairs.append(InlinePair(frame[2], frame[3], i, i + 2))
            else:
                paint(i, i + 2, kind)
            i += 2
            continue

        if text.startswith(r"\[", i):
            if kind == "TEXT":
                paint(i, i + 2, "DISPLAY_MATH")
                stack.append(("DISPLAY_MATH", None, i, i + 2))
            else:
                paint(i, i + 2, kind)
            i += 2
            continue

        if text.startswith(r"\]", i):
            if stack and stack[-1][0] == "DISPLAY_MATH" and stack[-1][1] is None:
                paint(i, i + 2, "DISPLAY_MATH")
                stack.pop()
            else:
                paint(i, i + 2, kind)
            i += 2
            continue

        m = re.match(r"\\(begin|end)\{([A-Za-z*]+)\}", text[i:])
        if m:
            full_end = i + m.end()
            action, env = m.group(1), m.group(2)
            kind = current_math_kind(stack)
            if action == "begin" and env in DISPLAY_ENVS:
                paint(i, full_end, "DISPLAY_MATH")
                stack.append(("DISPLAY_MATH", env, i, full_end))
            elif action == "begin" and env in NESTED_DISPLAY_ENVS and kind == "DISPLAY_MATH":
                paint(i, full_end, "DISPLAY_MATH")
                stack.append(("DISPLAY_MATH", env, i, full_end))
            elif action == "end" and stack and stack[-1][1] == env:
                paint(i, full_end, current_math_kind(stack))
                stack.pop()
            else:
                paint(i, full_end, kind)
            i = full_end
            continue

        region[i] = kind
        i += 1

    for frame in stack:
        if frame[0] == "INLINE_MATH":
            unmatched_inline.append(frame[2])
    return region, inline_pairs, unmatched_inline


def exact_proof_ending_exception(text: str, open_pos: int) -> bool:
    line_start = text.rfind("\n", 0, open_pos) + 1
    line_end = text.find("\n", open_pos)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].rstrip()
    suffix = r"\hfill\(\square\)"
    if not line.endswith(suffix):
        return False
    suffix_start = line_start + len(line) - len(suffix)
    expected_open = suffix_start + len(r"\hfill")
    return open_pos == expected_open


def find_balanced_brace_end(text: str, brace_pos: int) -> int:
    if brace_pos >= len(text) or text[brace_pos] != "{":
        return brace_pos
    depth = 0
    i = brace_pos
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def mask_machine_regions(text: str, math_region: list[str]) -> str:
    """Mask math and reliable machine-identifier regions for L018, preserving line mapping."""
    chars = list(text)
    for i, kind in enumerate(math_region):
        if kind != "TEXT" and chars[i] != "\n":
            chars[i] = " "

    masked = "".join(chars)
    chars = list(masked)

    command_re = re.compile(r"\\([A-Za-z@]+)\*?\s*\{")
    for m in command_re.finditer(masked):
        cmd = m.group(1)
        if cmd not in MACHINE_ARG_COMMANDS and cmd not in {"begin", "end", "href"}:
            continue
        brace_pos = masked.find("{", m.start(), m.end())
        if brace_pos < 0:
            continue
        end = find_balanced_brace_end(masked, brace_pos)
        mask_region(chars, brace_pos, end)

    prose = "".join(chars)
    chars = list(prose)

    # TikZ node/coordinate identifiers are machine syntax, not Chinese prose delimiters.
    offset = 0
    for line in prose.splitlines(keepends=True):
        if r"\node" in line or r"\draw" in line:
            for m in re.finditer(r"\([A-Za-z0-9_.:-]+\)", line):
                mask_region(chars, offset + m.start(), offset + m.end())
        offset += len(line)

    prose = "".join(chars)
    chars = list(prose)
    for pat in (
        r"https?://[^\s{}]+",
        r"www\.[^\s{}]+",
        r"(?:[A-Za-z]:)?(?:[/\\][^\s{}]+)+",
        r"[A-Za-z0-9_.-]+\.(?:tex|sty|cls|bib|md|pdf|zip|py)(?:[/\\][^\s{}]+)*",
    ):
        for m in re.finditer(pat, prose):
            mask_region(chars, m.start(), m.end())
    return "".join(chars)


def is_cjk(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
    )


def nearest_nonspace(text: str, pos: int, step: int) -> str:
    i = pos + step
    while 0 <= i < len(text) and text[i] in " \t\r":
        i += step
    if 0 <= i < len(text) and text[i] != "\n":
        return text[i]
    return ""


def l018_findings(path: Path, text: str, math_region: list[str], starts: list[int]) -> tuple[list[Finding], list[Finding]]:
    hard: list[Finding] = []
    manual: list[Finding] = []
    prose = mask_machine_regions(text, math_region)

    for pos, ch in enumerate(prose):
        if ch not in ",;:?!":
            continue
        left = nearest_nonspace(prose, pos, -1)
        right = nearest_nonspace(prose, pos, 1)
        if is_cjk(left) or is_cjk(right):
            hard.append(Finding("L018", path, line_number(starts, pos), f"ASCII punctuation {ch!r} used in Chinese prose"))

    # ASCII parentheses and quotes are context-sensitive: report as manual candidates when
    # they are adjacent to Chinese text or visibly delimit Chinese on the same line.
    for pos, ch in enumerate(prose):
        if ch not in "()\"'":
            continue
        left = nearest_nonspace(prose, pos, -1)
        right = nearest_nonspace(prose, pos, 1)
        line_start = prose.rfind("\n", 0, pos) + 1
        line_end = prose.find("\n", pos)
        if line_end < 0:
            line_end = len(prose)
        lo = max(line_start, pos - 80)
        hi = min(line_end, pos + 81)
        neighborhood = prose[lo:hi]
        if is_cjk(left) or is_cjk(right) or any(is_cjk(c) for c in neighborhood):
            manual.append(Finding("L018", path, line_number(starts, pos), f"ASCII delimiter {ch!r} in Chinese prose requires manual adjudication", "MANUAL"))
    return hard, manual


def is_positive_spacing_token(tok: Token) -> bool:
    return (tok.kind == "word" and tok.value in {"quad", "qquad"}) or (
        tok.kind == "symbol" and tok.value in {",", ";", ":", " "}
    )


def display_preceding_blank_findings(path: Path, text: str, starts: list[int]) -> list[Finding]:
    """Flag a literal blank source line immediately before a top-level display opener."""
    findings: list[Finding] = []
    lines = text.splitlines(keepends=True)
    offset = 0
    offsets: list[int] = []
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    for i, line in enumerate(lines):
        if i == 0 or DISPLAY_OPEN_LINE_RE.match(line) is None:
            continue
        if lines[i - 1].strip() == "":
            findings.append(Finding(
                "L019", path, line_number(starts, offsets[i]),
                "blank source line immediately before display mathematics is forbidden",
            ))
    return findings


def scan_file(path: Path) -> tuple[list[Finding], list[Finding]]:
    raw = path.read_text(encoding="utf-8")
    text = mask_noncode(raw)
    starts = line_starts(text)
    tokens = list(iter_tokens(text))
    math_region, inline_pairs, unmatched_inline = parse_math_regions(text)
    hard: list[Finding] = []
    heuristic: list[Finding] = []

    for tok in tokens:
        if tok.kind == "word" and tok.value in HARD_WORD_RULES:
            rule, msg = HARD_WORD_RULES[tok.value]
            hard.append(Finding(rule, path, line_number(starts, tok.start), msg))
        if tok.kind == "word" and tok.value in {"forall", "exists"}:
            if text[tok.end:tok.end + 2] != r"\,":
                hard.append(Finding("L014", path, line_number(starts, tok.start), rf"\\{tok.value} must be followed immediately by \\,"))
        if tok.kind == "word" and tok.value == "qquad":
            hard.append(Finding("L015", path, line_number(starts, tok.start), r"\qquad is forbidden in source text"))
        if tok.kind == "word" and tok.value == "quad" and math_region[tok.start] == "INLINE_MATH":
            hard.append(Finding("L016", path, line_number(starts, tok.start), r"\quad is forbidden in inline mathematics"))
        if tok.kind == "word" and tok.value in {"hspace", "hskip", "kern", "mkern"} and math_region[tok.start] != "TEXT":
            heuristic.append(Finding("L017", path, line_number(starts, tok.start), rf"custom mathematical spacing command \\{tok.value} requires manual adjudication", "HEURISTIC"))

    for pos, ch in enumerate(text):
        if ch == "\u3002":
            hard.append(Finding("L007", path, line_number(starts, pos), "Chinese full stop is forbidden; use ASCII period"))

    token_by_start = {tok.start: tok for tok in tokens}
    for pos, ch in enumerate(text):
        if ch != "$":
            continue
        prev = token_by_start.get(pos - 1)
        if prev is not None and prev.kind == "symbol" and prev.value == "$" and prev.end == pos + 1:
            continue
        hard.append(Finding("L008", path, line_number(starts, pos), "unescaped dollar delimiter is forbidden"))

    for pair in inline_pairs:
        if exact_proof_ending_exception(text, pair.open_pos):
            continue
        content = text[pair.content_start:pair.content_end].lstrip()
        if re.match(r"\\displaystyle(?![A-Za-z@])", content) is None:
            hard.append(Finding("L009", path, line_number(starts, pair.open_pos), r"inline math must begin with \displaystyle"))
    for pos in unmatched_inline:
        hard.append(Finding("L009", path, line_number(starts, pos), "inline math opener has no matching closer"))

    # Existing conservative heuristic rules.
    for m in re.finditer(r"\^\s*(?:T|\{T\}|\\top(?![A-Za-z@]))", text):
        heuristic.append(Finding("L011", path, line_number(starts, m.start()), "possible noncanonical transpose notation", "HEURISTIC"))
    for m in re.finditer(r"\^\s*(?:H|\{H\}|\\dagger(?![A-Za-z@]))", text):
        heuristic.append(Finding("L012", path, line_number(starts, m.start()), "possible noncanonical conjugate-transpose notation", "HEURISTIC"))
    for m in re.finditer(r"\\int(?![A-Za-z@])", text):
        line_end = text.find("\n", m.start())
        if line_end < 0:
            line_end = len(text)
        segment = text[m.start():line_end]
        bad = False
        for dm in re.finditer(r"\\mathrm\{d\}", segment):
            absolute = m.start() + dm.start()
            if text[max(0, absolute - 2):absolute] != r"\,":
                bad = True
                break
        if not bad and re.search(r"(?<![A-Za-z\\])d[xts](?![A-Za-z])", segment):
            bad = True
        if bad:
            heuristic.append(Finding("L013", path, line_number(starts, m.start()), "possible noncanonical integral differential", "HEURISTIC"))

    # Positive explicit spacing stacking candidates, only inside mathematics.
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if math_region[tok.start] == "TEXT" or not is_positive_spacing_token(tok):
            i += 1
            continue
        seq = [tok]
        j = i + 1
        while j < len(tokens):
            nxt = tokens[j]
            if math_region[nxt.start] != math_region[tok.start] or not is_positive_spacing_token(nxt):
                break
            gap = text[seq[-1].end:nxt.start]
            if gap.strip() != "":
                break
            seq.append(nxt)
            j += 1
        if len(seq) >= 2:
            heuristic.append(Finding("SPACING_STACKING_MANUAL_QA", path, line_number(starts, tok.start), "consecutive positive explicit spacing commands require manual adjudication", "HEURISTIC"))
            i = j
        else:
            i += 1

    l018_hard, l018_manual = l018_findings(path, text, math_region, starts)
    hard.extend(l018_hard)
    heuristic.extend(l018_manual)
    hard.extend(display_preceding_blank_findings(path, text, starts))

    return hard, heuristic


def discover_sources(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix in SCAN_SUFFIXES else []
    excluded = {".git", "build", "_build", "renders", "qa/renders"}
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == x or rel.startswith(x + "/") for x in excluded):
            continue
        out.append(path)
    return sorted(out)


def run(root: Path) -> tuple[list[Finding], list[Finding], list[Path]]:
    hard: list[Finding] = []
    heuristic: list[Finding] = []
    sources = discover_sources(root)
    for src in sources:
        h, q = scan_file(src)
        hard.extend(h)
        heuristic.extend(q)
    return hard, heuristic, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Token-aware LaTeX linter")
    parser.add_argument("project_root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    hard, heuristic, sources = run(root)
    for f in sorted(hard + heuristic, key=lambda x: (str(x.path), x.line, x.rule, x.message)):
        try:
            shown = f.path.relative_to(root)
        except ValueError:
            shown = f.path
        print(f"{f.severity} {f.rule} {shown}:{f.line}: {f.message}")
    print(f"SCANNED_FILES={len(sources)} HARD_FINDINGS={len(hard)} HEURISTIC_CANDIDATES={len(heuristic)}")
    if hard:
        print("HARD_LINT=FAIL")
        return 1
    print("HARD_LINT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
