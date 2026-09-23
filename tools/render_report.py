#!/usr/bin/env python3
"""Fill templates/test_report.html from reports/junit.xml (no extra deps)."""

from __future__ import annotations

import html
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "reports" / "junit.xml"
TEMPLATE = ROOT / "templates" / "test_report.html"
OUT = ROOT / "reports" / "index.html"


def main() -> int:
    if not JUNIT.exists():
        print(f"missing {JUNIT}; run pytest first", file=sys.stderr)
        return 1
    tree = ET.parse(JUNIT)
    suites = list(tree.iter("testsuite"))
    if not suites:
        print("no testsuite in junit xml", file=sys.stderr)
        return 1
    tests = passed = failed = skipped = 0
    duration = 0.0
    rows = []
    for suite in suites:
        tests += int(suite.attrib.get("tests", 0))
        failed += int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
        skipped += int(suite.attrib.get("skipped", 0))
        duration += float(suite.attrib.get("time", 0) or 0)
        for case in suite.findall("testcase"):
            name = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
            t = case.attrib.get("time", "0")
            detail = ""
            result = "PASS"
            css = "ok"
            if case.find("failure") is not None or case.find("error") is not None:
                result = "FAIL"
                css = "fail"
                node = case.find("failure") if case.find("failure") is not None else case.find("error")
                detail = (node.attrib.get("message") or (node.text or ""))[:200]
            elif case.find("skipped") is not None:
                result = "SKIP"
                css = "skip"
            rows.append(
                f"<tr><td class='{css}'>{result}</td><td><code>{html.escape(name)}</code></td>"
                f"<td>{html.escape(t)}</td><td>{html.escape(detail)}</td></tr>"
            )
    passed = tests - failed - skipped
    template = TEMPLATE.read_text(encoding="utf-8")
    out = (
        template.replace("{{tests}}", str(tests))
        .replace("{{passed}}", str(passed))
        .replace("{{failed}}", str(failed))
        .replace("{{skipped}}", str(skipped))
        .replace("{{time}}", f"{duration:.3f}")
        .replace("{{rows}}", "\n      ".join(rows))
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
