"""Stand-in for the detect-indent package (NameRTS uses only detect_indent(text)['indent']): the most common
indentation step between consecutive indented lines, as detect-indent computes it."""
from collections import Counter


def detect_indent(text):
    steps = Counter()
    prev = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        ws = line[: len(line) - len(stripped)]
        width = len(ws.expandtabs(4))
        if "\t" in ws:
            steps["\t"] += 1
        elif width != prev and width > 0:
            steps[" " * abs(width - prev)] += 1
        prev = width
    indent = steps.most_common(1)[0][0] if steps else ""
    return {"amount": len(indent), "type": "tab" if indent == "\t" else ("space" if indent else None),
            "indent": indent}
