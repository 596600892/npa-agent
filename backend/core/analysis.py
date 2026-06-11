from __future__ import annotations

from .attribution import build_attributions
from .data_quality import data_quality
from .disposition import select_disposition
from .history_calibrator import build_pricing_calibration
from .pricing import pricing_scenarios
from .profile_analyzer import analyze_profile
from .report_writer import write_report


def run_analysis(
    project: dict,
    accounts: list[dict],
    history_records: list[dict] | None = None,
    court_profiles: list[dict] | None = None,
    legal_risk: dict | None = None,
    execution_summary: dict | None = None,
) -> dict:
    quality = data_quality(accounts)
    profile = analyze_profile(accounts)
    disposition = select_disposition(accounts, quality, profile)
    calibration = build_pricing_calibration(project, accounts, history_records or [], court_profiles or [])
    pricing = pricing_scenarios(quality, profile, calibration, legal_risk)
    attributions = build_attributions(quality, profile, disposition, legal_risk)
    report = write_report(project, quality, profile, disposition, pricing, attributions, legal_risk, execution_summary)
    return {
        "quality": quality,
        "profile": profile,
        "disposition": disposition,
        "pricing": pricing,
        "calibration": calibration,
        "legal_risk": legal_risk,
        "execution_summary": execution_summary,
        "attributions": attributions,
        "report": report,
    }
