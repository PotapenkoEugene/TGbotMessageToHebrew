import html


def build_explain_table(payload: dict) -> str:
    rows = payload.get("rows", [])
    context = payload.get("context", "")

    lines: list[str] = []
    for r in rows:
        he = r.get("he", "").strip()
        ru = r.get("ru", "").strip()
        base = r.get("base", "").strip()
        if not he or not ru:
            continue
        if base and base != he:
            lines.append(f"{he} — {ru} — {base}")
        else:
            lines.append(f"{he} — {ru}")

    result = html.escape("\n".join(lines))
    if context:
        result += f"\n\n{html.escape(context)}"
    return result


def build_grammar_reply(payload: dict) -> str:
    issues = payload.get("issues", [])
    summary = payload.get("summary", "").strip()
    if not issues:
        return html.escape(summary) if summary else "Всё верно."
    lines: list[str] = []
    for it in issues:
        phrase = it.get("phrase", "").strip()
        suggest = it.get("suggest", "").strip()
        why = it.get("why", "").strip()
        if phrase and suggest:
            lines.append(f"{phrase} → {suggest} — {why}" if why else f"{phrase} → {suggest}")
    body = html.escape("\n".join(lines))
    if summary:
        body += f"\n\n{html.escape(summary)}"
    return body
