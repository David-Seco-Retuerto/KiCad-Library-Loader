"""Readable report blocks and semantic colors without altering the stored plan."""


def report_line(line):
    value = line.strip().casefold()
    if value.startswith(("warning:", "warning ", "files changed.")):
        return "warning", "warning"
    if value.startswith(("error:", "cannot ", "could not ", "invalid ", "failed ", "import cancelled:", "restore blocked", "update blocked", "removal blocked", "recovery blocked", "svg preview unavailable:")):
        return "error", "error"
    if value.startswith(("plan valid.", "import completed.", "component updated.", "component moved.", "component removed.", "component restored.", "component recovered.", "library folders prepared.", "svg opened", "step preview ok", "downloaded ")):
        return "success", "result"
    groups = (
        ("locations", ("input folder:", "library output root:", "import history folder:", "library root:", "output root:")),
        ("model_paths", ("kicad path variable:",)),
        ("symbol", ("symbol output:", "symbol destination:")),
        ("registration", ("register ", "library nickname:")),
        ("files", ("write:", "reuse unchanged:", "remove after backup:", "create folder:", "keep shared ")),
    )
    for group, prefixes in groups:
        if value.startswith(prefixes):
            return "info", group
    return "info", "details"


def report_lines(text):
    """Preserve each message and insert one blank line between semantic blocks."""
    previous, blank = None, True
    for line in str(text).splitlines():
        if not line.strip():
            if not blank:
                yield "", "info"
            blank = True
            previous = None
            continue
        tag, group = report_line(line)
        if previous is not None and group != previous and not blank:
            yield "", "info"
        yield line, tag
        previous, blank = group, False
