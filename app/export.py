from __future__ import annotations

from collections.abc import Mapping, Sequence


def timestamp(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"


def build_package(claims: Sequence[Mapping[str, object]], segments: Mapping[str, object]) -> dict[str, object]:
    approved = [claim for claim in claims if claim["approved"]]
    evidence: list[dict[str, str]] = []
    for claim in approved:
        for segment_id in str(claim["evidence_ids"]).split(","):
            segment = segments[segment_id]
            evidence.append(
                {
                    "segment_id": segment.id,
                    "start": timestamp(segment.start),
                    "end": timestamp(segment.end),
                    "quote": segment.text,
                }
            )
    unique_evidence = list({item["segment_id"]: item for item in evidence}.values())
    starts = [item["start"] for item in unique_evidence]
    ends = [item["end"] for item in unique_evidence]
    return {
        "project": "ApexFlow product webinar",
        "clip": {"start": min(starts, default="00:00"), "end": max(ends, default="00:00")},
        "hook": "Proof beats promises",
        "caption": "Publish only the language your source can support.",
        "post_copy": " ".join(str(claim["rewrite"]) for claim in approved),
        "claims": [
            {
                "text": str(claim["rewrite"]),
                "status": "approved",
                "reason": str(claim["reason"]),
                "evidence_ids": str(claim["evidence_ids"]).split(","),
            }
            for claim in approved
        ],
        "evidence": unique_evidence,
    }


def markdown(package: Mapping[str, object]) -> str:
    clip = package["clip"]
    claims = package["claims"]
    evidence = package["evidence"]
    lines = [
        f"# {package['project']}",
        "",
        f"**Clip:** {clip['start']} - {clip['end']}",
        f"**Hook:** {package['hook']}",
        f"**Caption:** {package['caption']}",
        "",
        "## Post copy",
        str(package["post_copy"]) or "No claims are approved yet.",
        "",
        "## Approved claims",
    ]
    lines.extend(f"- {claim['text']}" for claim in claims) or lines.append("- No claims are approved yet.")
    lines.extend(["", "## Evidence"])
    lines.extend(f"- [{item['start']} - {item['end']}] {item['quote']} ({item['segment_id']})" for item in evidence)
    return "\n".join(lines) + "\n"
