"""Mechanical calculations for the Rev E master layout. Every result is evidence class `calculated`."""


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def inputs_table(inputs):
    return table(["Input", "Value", "Unit", "Source / status"], inputs)


def f(x, n=1):
    return f"{x:.{n}f}"
