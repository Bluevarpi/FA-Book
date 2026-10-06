#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import lint

CN = {
    "zhongwen": "\u4e2d\u6587",
    "wenben": "\u6587\u672c",
    "jixu": "\u7ee7\u7eed",
    "shuoming": "\u8bf4\u660e",
    "keyi": "\u53ef\u4ee5",
    "jumo": "\u53e5\u672b",
    "wenti": "\u95ee\u9898",
    "daan": "\u7b54\u6848",
    "zhuyi": "\u6ce8\u610f",
    "xueximubiao": "\u5b66\u4e60\u76ee\u6807",
    "neirong": "\u5185\u5bb9",
}

VALID = r"""
\documentclass{article}
\begin{document}
\(\displaystyle x\)
\(\displaystyle x\,y\)
\(\displaystyle x\;y\)
\(\displaystyle x\ y\)
A proof sentence.\hfill\(\square\)
\varphi \varepsilon \leqslant \geqslant \left( x \right) \geometry \$ \forall\,x \exists\,x
Text mode \quad is legal.
\textbf{PLACEHOLDER}\quad PLACEHOLDER2
\[
x\quad y
\]
\begin{equation}
x\quad y
\end{equation}
\begin{align}
x&=y\quad z\\
\begin{aligned}
a&=b\quad c
\end{aligned}
\end{align}
\label{chap:I-01}
\autoref{sec:a:b}
\url{https://example.com/a:b/c}
\(\displaystyle f(x,y):=x+y\)
% \phi \epsilon \le \ge \exp \qed $x$ \qquad \quad
\begin{verbatim}
\phi \epsilon \le \ge \exp \qed $x$ \qquad \quad
\end{verbatim}
\verb|\phi \epsilon \le \ge \exp \qed $x$ \qquad \quad|
\end{document}
"""
VALID = VALID.replace("PLACEHOLDER", CN["xueximubiao"], 1).replace("PLACEHOLDER2", CN["neirong"], 1)
VALID += CN["zhongwen"] + "\uff0c" + CN["wenben"] + "\uff1b" + CN["jixu"] + "\uff1a" + CN["shuoming"] + "\uff1f" + CN["keyi"] + "\uff01" + CN["jumo"] + ".\n"

INVALID_CASES = {
    "L009-inline": (r"\(x\)", "L009"),
    "L003-phi": (r"\phi", "L003"),
    "L002-epsilon": (r"\epsilon", "L002"),
    "L004-le": (r"\le", "L004"),
    "L004-leq": (r"\leq", "L004"),
    "L005-ge": (r"\ge", "L005"),
    "L005-geq": (r"\geq", "L005"),
    "L006-exp": (r"\exp", "L006"),
    "L010-qed": (r"\qed", "L010"),
    "L010-qedhere": (r"\qedhere", "L010"),
    "L008-dollar": (r"$x$", "L008"),
    "L007-period": ("\u3002", "L007"),
    "L014-forall": (r"\forall x", "L014"),
    "L014-exists": (r"\exists x", "L014"),
    "L009-square": (r"\(\square\)", "L009"),
}

NEW_HARD_CASES = {
    "L016-inline-quad": (r"\(\displaystyle x\quad y\)", "L016"),
    "L015-text-qquad": (r"Text \qquad text", "L015"),
    "L015-inline-qquad": (r"\(\displaystyle x\qquad y\)", "L015"),
    "L015-display-qquad": ("\\[\nx\\qquad y\n\\]", "L015"),
    "L015-equation-qquad": ("\\begin{equation}\nx\\qquad y\n\\end{equation}", "L015"),
    "L015-align-qquad": ("\\begin{align}\nx&=y\\qquad z\n\\end{align}", "L015"),
    "L018-comma": (CN["zhongwen"] + "," + CN["wenben"] + ".", "L018"),
    "L018-semicolon": (CN["zhongwen"] + ";" + CN["wenben"] + ".", "L018"),
    "L018-colon": (CN["shuoming"] + ":" + CN["neirong"] + ".", "L018"),
    "L018-question": (CN["wenti"] + "?" + CN["daan"] + ".", "L018"),
    "L018-bang": (CN["zhuyi"] + "!" + CN["neirong"] + ".", "L018"),
    "L019-display-blank": ("前文.\n\n\\[\nx=y\n\\]", "L019"),
    "L019-equation-blank": ("前文.\n\n\\begin{equation}\nx=y\n\\end{equation}", "L019"),
}

NEW_HEURISTIC_CASES = {
    "L017-hspace": (r"\(\displaystyle x\hspace{1em}y\)", "L017"),
    "L017-mkern": (r"\(\displaystyle x\mkern10mu y\)", "L017"),
    "stack-quad": ("\\[\nx\\quad\\quad y\n\\]", "SPACING_STACKING_MANUAL_QA"),
    "stack-thin": (r"\(\displaystyle x\,\,\,y\)", "SPACING_STACKING_MANUAL_QA"),
    "stack-semicolon": (r"\(\displaystyle x\;\;y\)", "SPACING_STACKING_MANUAL_QA"),
    "stack-colon": (r"\(\displaystyle x\:\:y\)", "SPACING_STACKING_MANUAL_QA"),
    "stack-control-space": (r"\(\displaystyle x\ \ y\)", "SPACING_STACKING_MANUAL_QA"),
    "stack-mixed": (r"\(\displaystyle x\,\;y\)", "SPACING_STACKING_MANUAL_QA"),
}


def scan_text(text: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "case.tex"
        p.write_text(text, encoding="utf-8")
        hard, heur = lint.scan_file(p)
        return hard, heur


def assert_hard(snippet: str, expected: str, name: str) -> None:
    hard, _ = scan_text("\\documentclass{article}\n\\begin{document}\n" + snippet + "\n\\end{document}\n")
    rules = {f.rule for f in hard}
    assert expected in rules, f"{name}: expected {expected}, got {rules}"


def assert_heuristic(snippet: str, expected: str, name: str) -> None:
    hard, heur = scan_text("\\documentclass{article}\n\\begin{document}\n" + snippet + "\n\\end{document}\n")
    assert not [f for f in hard if f.rule == expected], f"{name}: unexpected hard {hard}"
    rules = {f.rule for f in heur}
    assert expected in rules, f"{name}: expected heuristic {expected}, got {rules}"


def parser_regression() -> None:
    sample = r"""Text \quad.
\(\displaystyle a\quad b\)
\[
c\quad d
\begin{aligned}
e&=f\quad g
\end{aligned}
\]
"""
    masked = lint.mask_noncode(sample)
    region, pairs, unmatched = lint.parse_math_regions(masked)
    assert not unmatched
    assert len(pairs) == 1
    text_quad = sample.index(r"\quad")
    inline_quad = sample.index(r"\quad", text_quad + 1)
    display_quad = sample.index(r"\quad", inline_quad + 1)
    aligned_quad = sample.index(r"\quad", display_quad + 1)
    assert region[text_quad] == "TEXT"
    assert region[inline_quad] == "INLINE_MATH"
    assert region[display_quad] == "DISPLAY_MATH"
    assert region[aligned_quad] == "DISPLAY_MATH"

    hard, _ = scan_text(sample)
    rules_by_line = {(f.rule, f.line) for f in hard}
    assert any(f.rule == "L016" and f.line == 2 for f in hard), rules_by_line
    assert not any(f.rule == "L016" and f.line in {1, 4, 6} for f in hard), rules_by_line

    qsample = "\\(\\displaystyle a\\qquad b\\)\n\\[c\\qquad d\\]"
    hard, _ = scan_text(qsample)
    assert sum(f.rule == "L015" for f in hard) == 2, hard

    masked_lines = "% bad \\qquad\nA\n\\begin{verbatim}\nbad \\qquad\n\\end{verbatim}\nB\n"
    hard, _ = scan_text(masked_lines)
    assert not any(f.rule == "L015" for f in hard), hard

    line_map_sample = "% masked\n\\begin{verbatim}\nmasked \\quad\n\\end{verbatim}\ntext\n\\(\\displaystyle x\\quad y\\)\n"
    hard, _ = scan_text(line_map_sample)
    l016 = [f for f in hard if f.rule == "L016"]
    assert len(l016) == 1 and l016[0].line == 6, l016

    hard, heur = scan_text("Proof.\\hfill\\(\\square\\)\n")
    assert not hard, hard
    assert not any(f.rule == "L017" for f in heur), heur


def l018_boundary_regression() -> None:
    paren = CN["zhongwen"] + "(" + CN["shuoming"] + ")" + CN["wenben"] + "."
    quote = CN["zhongwen"] + '"' + CN["shuoming"] + '"' + CN["wenben"] + "."
    for sample in (paren, quote):
        hard, heur = scan_text(sample)
        assert not any(f.rule == "L018" for f in hard), hard
        assert any(f.rule == "L018" and f.severity == "MANUAL" for f in heur), heur

    safe = CN["zhongwen"] + r" \label{chap:I-01} \url{https://example.com/a:b/c} " + CN["wenben"] + "."
    hard, heur = scan_text(safe)
    assert not any(f.rule == "L018" for f in hard + heur), hard + heur

    math_punct = CN["zhongwen"] + r" \(\displaystyle f(x,y):=x+y\) " + CN["wenben"] + "."
    hard, heur = scan_text(math_punct)
    assert not any(f.rule == "L018" for f in hard + heur), hard + heur


def main() -> int:
    hard, heur = scan_text(VALID)
    assert not hard, f"valid sample produced hard findings: {hard}"
    assert not heur, f"valid sample produced heuristic findings: {heur}"

    for name, (snippet, expected) in INVALID_CASES.items():
        assert_hard(snippet, expected, name)

    for name, (snippet, expected) in NEW_HARD_CASES.items():
        assert_hard(snippet, expected, name)

    for name, (snippet, expected) in NEW_HEURISTIC_CASES.items():
        assert_heuristic(snippet, expected, name)

    hard, _ = scan_text("Logic sentence.\\hfill\\(\\square\\)\n")
    assert not hard, f"proof-ending exception should pass: {hard}"

    hard, _ = scan_text("\\(\\square\\)\n")
    assert any(f.rule == "L009" for f in hard), "ordinary square inline math must fail L009"

    comment_and_verbatim = r"""
% \phi \epsilon \le \ge \exp \qed $x$ \u3002 \(x\) \qquad \quad
\begin{verbatim}
\phi \epsilon \le \ge \exp \qed $x$ \qquad \quad
\end{verbatim}
\verb|\phi \epsilon \le \ge \exp \qed $x$ \qquad \quad|
"""
    hard, _ = scan_text(comment_and_verbatim)
    assert not hard, f"masked regions should not produce findings: {hard}"

    prefix_legality = r"\varphi \varepsilon \leqslant \geqslant \left \geometry \$ \forall\,x \exists\,x"
    hard, _ = scan_text(prefix_legality)
    assert not hard, f"legal complete tokens were misclassified: {hard}"

    parser_regression()
    l018_boundary_regression()

    print("LINT_UNIT_TEST=PASS")
    print(f"ORIGINAL_INVALID_CASES_VERIFIED={len(INVALID_CASES)}")
    print(f"NEW_HARD_CASES_VERIFIED={len(NEW_HARD_CASES)}")
    print(f"NEW_HEURISTIC_CASES_VERIFIED={len(NEW_HEURISTIC_CASES)}")
    print("MATH_REGION_PARSER_QA=PASS")
    print("COMMENT_VERBATIM_MASKING=PASS")
    print("PROOF_ENDING_EXCEPTION=PASS")
    print("PREFIX_TOKEN_GUARDS=PASS")
    print("L018_BOUNDARY_QA=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
