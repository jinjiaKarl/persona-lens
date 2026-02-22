from datetime import date
from typing import Any


def format_agent_report(result: dict[str, Any]) -> str:
    """Format agent result dict into a Markdown report string."""
    users = result.get("users", {})
    engagement = result.get("engagement", {})
    matches = result.get("matches", [])

    sections = [f"# KOL Batch Analysis Report\n\n*Generated {date.today()}*\n"]

    if engagement:
        sections.append("## Insights\n")
        sections.append(engagement.get("insights", "") + "\n")
        patterns = engagement.get("patterns", [])
        if patterns:
            sections.append("\n**Key patterns:**\n")
            for p in patterns:
                sections.append(f"- **{p.get('type', '')}**: {p.get('description', '')}")
        sections.append("")

    sections.append("## Per-Account Analysis\n")
    for username, data in users.items():
        patterns = data.get("patterns", {})
        products = data.get("products", [])
        peak_days = patterns.get("peak_days", {})
        peak_hours = patterns.get("peak_hours", {})

        top_day = max(peak_days, key=peak_days.get) if peak_days else "N/A"
        top_hour = max(peak_hours, key=peak_hours.get) if peak_hours else "N/A"

        sections.append(f"### @{username}\n")
        sections.append(f"- **Peak posting**: {top_day}, {top_hour} UTC")
        if products:
            product_names = ", ".join(p["product"] for p in products[:8])
            sections.append(f"- **Products mentioned**: {product_names}")
            categories = list({p["category"] for p in products})
            sections.append(f"- **Categories**: {', '.join(categories)}")
        sections.append("")

    if matches:
        sections.append("## Content Brief Matching\n")
        sections.append("| Content Brief | Best Fit | Reason |")
        sections.append("|---|---|---|")
        for m in matches:
            users_str = ", ".join(f"@{u}" for u in m.get("matched_users", []))
            brief = m.get("brief", "")[:50]
            reason = m.get("reason", "")
            sections.append(f"| {brief} | {users_str} | {reason} |")
        sections.append("")

    return "\n".join(sections)
