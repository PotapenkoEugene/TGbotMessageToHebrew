import html

_HEADERS = ("Слово", "База", "Произн.", "Перевод")


def build_explain_table(payload: dict) -> str:
    rows = payload.get("rows", [])
    context = payload.get("context", "")

    data = [
        (r.get("he", ""), r.get("base", ""), r.get("pron", ""), r.get("ru", ""))
        for r in rows
    ]
    all_rows = [_HEADERS] + data
    widths = [max(len(row[i]) for row in all_rows) for i in range(4)]

    def fmt(row: tuple) -> str:
        return " | ".join(row[i].ljust(widths[i]) for i in range(4))

    sep = "-+-".join("-" * w for w in widths)
    lines = [fmt(_HEADERS), sep] + [fmt(r) for r in data]
    table = "\n".join(lines)

    result = f"<pre>{html.escape(table)}</pre>"
    if context:
        result += f"\n\n{html.escape(context)}"
    return result
