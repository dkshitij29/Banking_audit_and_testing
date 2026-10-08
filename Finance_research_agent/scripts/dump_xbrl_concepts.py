"""Discovery tool: dump all XBRL concepts from an instance file.

Usage:
    python scripts/dump_xbrl_concepts.py <file.xbrl>
"""

import sys
from pathlib import Path
from collections import defaultdict

import lxml.etree as ET


_NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
}


def main():
    if len(sys.argv) < 2:
        print("Usage: dump_xbrl_concepts.py <file.xbrl|xml>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    tree = ET.parse(str(path))
    root = tree.getroot()

    # Parse contexts
    contexts = {}
    for ctx in root.iter(f"{{{_NS['xbrli']}}}context"):
        ctx_id = ctx.get("id")
        period_el = ctx.find(f"{{{_NS['xbrli']}}}period", _NS)
        period_type = "instant" if period_el.find(f"{{{_NS['xbrli']}}}instant", _NS) is not None else "duration"
        contexts[ctx_id] = {
            "type": period_type,
            "has_dims": False,
        }

        segment = ctx.find(f"{{{_NS['xbrli']}}}segment", _NS)
        if segment is not None:
            if segment.findall(f".//{{{_NS['xbrldi']}}}explicitMember", _NS):
                contexts[ctx_id]["has_dims"] = True

    # Parse facts → group by concept
    facts = defaultdict(list)
    for fact in root.iter():
        tag = fact.tag
        local_name = tag.split("}")[-1] if "}" in tag else tag
        namespace = tag.split("{")[1].rstrip("}") if "{" in tag else "(default)"
        ctx_ref = fact.get("contextRef")
        value = fact.text or ""
        decimals = fact.get("decimals", "unknown")

        ctx_info = contexts.get(ctx_ref, {})
        is_dimensional = ctx_info.get("has_dims", False)

        facts[local_name].append({
            "namespace": namespace,
            "context": ctx_ref,
            "period_type": ctx_info.get("type", "?"),
            "dimensional": is_dimensional,
            "value": value,
            "decimals": decimals,
        })

    # Print sorted by magnitude (monetary facts)
    print(f"File: {path.name}")
    print(f"Concepts found: {len(facts)}")
    print()

    for concept, occurrences in sorted(facts.items()):
        non_dim = [o for o in occurrences if not o["dimensional"]]
        if not non_dim:
            continue

        # Show first non-dimensional value per context
        print(f"{concept}")
        print(f"  namespace: {occurrences[0]['namespace']}")
        print(f"  occurrences: {len(occurrences)} (non-dimensional: {len(non_dim)})")

        for o in non_dim[:3]:  # show first 3
            val_display = o["value"][:30] if o["value"] else "(empty)"
            print(f"    ctx={o['context']!r} type={o['period_type']} decimals={o['decimals']} value={val_display}")
        print()


if __name__ == "__main__":
    main()
