"""Explainable lead scoring for V-Base.

Two independent numbers are produced, never one opaque score:

* **Fit** — firmographic and completeness signals about whether this lead is
  the right kind of buyer (business email, decision-making role, company size,
  industry and geography targets, contactability).
* **Engagement** — driven *only* by real activity rows that a human or a
  configured integration actually wrote. Nothing here infers buying intent, and
  there is no floor: with no logged activity the engagement score is zero.

Every rule that fired is reported with its points and a human-readable reason,
so the UI can always explain a number. Weights, target industries, target
geographies and the target size band are operator-configurable; the defaults
below are used until someone changes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Free consumer mail providers. An address here is still a valid lead, it just
#: carries less weight than a work-domain address.
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "aol.com",
        "gmail.com",
        "gmx.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "mail.com",
        "outlook.com",
        "protonmail.com",
        "rediffmail.com",
        "yahoo.com",
        "ymail.com",
    }
)

#: Substrings that mark a decision-making role. Matched against the job title.
DECISION_MAKER_TOKENS: tuple[str, ...] = (
    "chief",
    "founder",
    "co-founder",
    "owner",
    "president",
    "partner",
    "principal",
    "managing director",
    "general manager",
    "head of",
    "director",
    "vice president",
    "vp",
    "ceo",
    "cto",
    "cfo",
    "coo",
    "cmo",
    "cio",
    "cro",
    "cpo",
    "svp",
    "evp",
)

DEFAULT_TARGET_INDUSTRIES: tuple[str, ...] = (
    "Software",
    "SaaS",
    "Data Analytics",
    "AI/ML",
    "FinTech",
    "Health Tech",
    "Information Technology",
    "Enterprise",
)

DEFAULT_TARGET_COUNTRIES: tuple[str, ...] = ("India", "United States", "United Kingdom", "Canada", "Germany")

#: Default target employee band — the mid-market segment.
DEFAULT_SIZE_BAND: tuple[int, int] = (11, 200)

#: The settings key the configurable weights are stored under.
SETTINGS_KEY = "lead_scoring"

#: How much of the blended total comes from fit rather than engagement.
FIT_WEIGHT = 0.7


def _has_text(value: Any) -> bool:
    return bool(value) and bool(str(value).strip())


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].strip().lower() or None


def is_free_email(email: str | None) -> bool:
    domain = _email_domain(email)
    return bool(domain) and domain in FREE_EMAIL_DOMAINS


def is_decision_maker(job_title: str | None, seniority: str | None) -> bool:
    haystack = " ".join(part for part in (job_title, seniority) if part).lower()
    if not haystack:
        return False
    return any(token in haystack for token in DECISION_MAKER_TOKENS)


@dataclass
class ScoringConfig:
    """Operator-tunable inputs to the scorer."""

    weights: dict[str, int] = field(default_factory=dict)
    target_industries: tuple[str, ...] = DEFAULT_TARGET_INDUSTRIES
    target_countries: tuple[str, ...] = DEFAULT_TARGET_COUNTRIES
    size_band: tuple[int, int] = DEFAULT_SIZE_BAND

    def weight(self, key: str) -> int:
        value = self.weights.get(key, DEFAULT_WEIGHTS.get(key, 0))
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return DEFAULT_WEIGHTS.get(key, 0)


#: ``rule key -> default weight``. Every rule's weight is an operator-tunable
#: setting; these are the values used until someone changes them.
DEFAULT_WEIGHTS: dict[str, int] = {
    "business_email": 15,
    "email_present": 10,
    "phone_present": 10,
    "linkedin_present": 8,
    "decision_maker": 15,
    "seniority_known": 5,
    "company_known": 10,
    "company_size_target": 10,
    "industry_fit": 8,
    "geography_fit": 9,
    "next_step_scheduled": 5,
    "consent_known": 5,
    "logged_interaction": 12,
    "recent_interaction": 8,
}


@dataclass
class RuleOutcome:
    key: str
    label: str
    kind: str  # "fit" | "engagement"
    weight: int
    earned: bool
    detail: str

    @property
    def points(self) -> int:
        return self.weight if self.earned else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "weight": self.weight,
            "points": self.points,
            "earned": self.earned,
            "detail": self.detail,
        }


@dataclass
class ScoreResult:
    fit_score: int
    engagement_score: int
    total_score: int
    rules: list[RuleOutcome]

    @property
    def breakdown(self) -> list[dict[str, Any]]:
        return [rule.as_dict() for rule in self.rules]


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def score_lead(
    lead: Any,
    *,
    config: ScoringConfig | None = None,
    activity_count: int = 0,
    recent_activity_count: int = 0,
) -> ScoreResult:
    """Score ``lead`` and return the number *and* the reason for every rule.

    ``activity_count`` / ``recent_activity_count`` must come from real activity
    rows; the caller queries them. Passing zeroes (no activity) is accurate, not
    a penalty.
    """
    config = config or ScoringConfig()
    rules: list[RuleOutcome] = []

    def add(key: str, label: str, kind: str, earned: bool, detail: str) -> None:
        rules.append(
            RuleOutcome(
                key=key,
                label=label,
                kind=kind,
                weight=config.weight(key),
                earned=earned,
                detail=detail,
            )
        )

    email = getattr(lead, "email", None)
    title = getattr(lead, "job_title", None)
    seniority = getattr(lead, "seniority", None)
    industry = getattr(lead, "industry", None)
    country = getattr(lead, "country", None)
    employees = getattr(lead, "employee_count", None)

    # ---- Fit -------------------------------------------------------------
    has_email = _has_text(email)
    free = is_free_email(email)
    add(
        "email_present",
        "Email address on file",
        "fit",
        has_email,
        "Email present" if has_email else "No email address yet",
    )
    add(
        "business_email",
        "Business (non-free) email domain",
        "fit",
        has_email and not free,
        email if has_email and not free else ("Free provider domain" if free else "No business email"),
    )
    add(
        "phone_present",
        "Phone number on file",
        "fit",
        _has_text(getattr(lead, "phone", None)),
        "Phone present" if _has_text(getattr(lead, "phone", None)) else "No phone number yet",
    )
    add(
        "linkedin_present",
        "LinkedIn profile on file",
        "fit",
        _has_text(getattr(lead, "linkedin_url", None)),
        "Profile linked" if _has_text(getattr(lead, "linkedin_url", None)) else "No LinkedIn profile",
    )

    decision = is_decision_maker(title, seniority)
    add(
        "decision_maker",
        "Decision-making role",
        "fit",
        decision,
        f"{title or seniority}" if decision else "Role does not read as a decision maker",
    )
    add(
        "seniority_known",
        "Seniority recorded",
        "fit",
        _has_text(seniority),
        f"Seniority: {seniority}" if _has_text(seniority) else "Seniority not recorded",
    )

    company_known = _has_text(getattr(lead, "company_name", None)) or getattr(lead, "company_id", None) is not None
    add(
        "company_known",
        "Company identified",
        "fit",
        bool(company_known),
        getattr(lead, "company_name", None) or "Company not identified",
    )

    low, high = config.size_band
    in_band = isinstance(employees, int) and low <= employees <= high
    add(
        "company_size_target",
        f"Headcount in target band ({low}-{high})",
        "fit",
        in_band,
        f"{employees} employees" if isinstance(employees, int) else "Headcount unknown",
    )

    industry_match = _has_text(industry) and any(
        target.lower() in str(industry).lower() for target in config.target_industries
    )
    add(
        "industry_fit",
        "Industry in target list",
        "fit",
        bool(industry_match),
        str(industry) if industry_match else (str(industry) if _has_text(industry) else "Industry unknown"),
    )

    country_match = _has_text(country) and any(
        target.lower() == str(country).strip().lower() for target in config.target_countries
    )
    add(
        "geography_fit",
        "Geography in target list",
        "fit",
        bool(country_match),
        str(country) if country_match else (str(country) if _has_text(country) else "Country unknown"),
    )

    scheduled = getattr(lead, "next_follow_up_at", None) is not None
    add(
        "next_step_scheduled",
        "Next follow-up scheduled",
        "fit",
        scheduled,
        "Follow-up scheduled" if scheduled else "No follow-up scheduled",
    )
    add(
        "consent_known",
        "Communication preference recorded",
        "fit",
        _has_text(getattr(lead, "consent_status", None)),
        str(getattr(lead, "consent_status", "") or "Consent not recorded"),
    )

    # ---- Engagement (real activity only) ---------------------------------
    add(
        "logged_interaction",
        "At least one interaction logged",
        "engagement",
        activity_count > 0,
        f"{activity_count} logged interaction(s)" if activity_count else "No interactions logged",
    )
    add(
        "recent_interaction",
        "Interaction in the last 30 days",
        "engagement",
        recent_activity_count > 0,
        f"{recent_activity_count} recent interaction(s)" if recent_activity_count else "No recent interaction",
    )

    # Both halves are reported on the same 0-100 scale. Fit is the absolute
    # weight earned; engagement is the percentage of the engagement weights
    # earned, so "no activity logged" is 0 rather than a fraction of a small
    # number. The blended total keeps engagement meaningful even when a lead
    # maxes out on completeness.
    fit_score = _clamp(sum(rule.points for rule in rules if rule.kind == "fit"))
    engagement_max = sum(config.weight(key) for key in DEFAULT_WEIGHTS if key in _ENGAGEMENT_KEYS)
    engagement_earned = sum(rule.points for rule in rules if rule.kind == "engagement")
    engagement_score = _clamp(round(100 * engagement_earned / engagement_max)) if engagement_max else 0
    total = _clamp(round(fit_score * FIT_WEIGHT + engagement_score * (1 - FIT_WEIGHT)))

    return ScoreResult(
        fit_score=fit_score,
        engagement_score=engagement_score,
        total_score=total,
        rules=rules,
    )


_ENGAGEMENT_KEYS = frozenset({"logged_interaction", "recent_interaction"})


def score_breakdown_or_empty(value: Any) -> list[dict[str, Any]]:
    """Normalise a stored ``score_breakdown`` column to a list of dicts."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def split_scores(breakdown: list[dict[str, Any]]) -> tuple[int, int]:
    """``(fit, engagement)`` from a stored breakdown.

    Uses the same definitions as :func:`score_lead`: fit is the absolute weight
    earned, engagement is the percentage of the engagement weights earned. The
    per-rule ``weight`` is persisted in the breakdown, so this stays correct even
    after an operator retunes the rules.
    """
    fit = sum(int(item.get("points", 0)) for item in breakdown if item.get("kind") == "fit")
    earned = sum(
        int(item.get("points", 0)) for item in breakdown if item.get("kind") == "engagement"
    )
    weight = sum(
        int(item.get("weight", 0)) for item in breakdown if item.get("kind") == "engagement"
    )
    engagement = _clamp(round(100 * earned / weight)) if weight else 0
    return _clamp(fit), engagement


def summarise(breakdown: list[dict[str, Any]]) -> str:
    """One-line explanation of a score for tooltips and exports."""
    earned = [item.get("label", "") for item in breakdown if item.get("earned")]
    if not earned:
        return "No scoring rules met yet."
    return "Met: " + ", ".join(earned)


# Re-exported so the API layer can build a config from a settings row without
# importing the rule table directly.
def build_config(raw: dict[str, Any] | None) -> ScoringConfig:
    """Build a :class:`ScoringConfig` from the stored settings value.

    Unknown keys are ignored and malformed values fall back to the defaults, so
    a bad settings row can never break scoring.
    """
    raw = raw or {}
    weights: dict[str, int] = {}
    for key, value in (raw.get("weights") or {}).items():
        if key not in DEFAULT_WEIGHTS:
            continue
        try:
            weights[key] = max(0, int(value))
        except (TypeError, ValueError):
            continue

    def _strings(name: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
        value = raw.get(name)
        if isinstance(value, list):
            cleaned = tuple(str(item).strip() for item in value if str(item).strip())
            if cleaned:
                return cleaned
        return fallback

    band = raw.get("size_band")
    size_band = DEFAULT_SIZE_BAND
    if isinstance(band, (list, tuple)) and len(band) == 2:
        try:
            low, high = int(band[0]), int(band[1])
            if 0 <= low <= high:
                size_band = (low, high)
        except (TypeError, ValueError):
            pass

    return ScoringConfig(
        weights=weights,
        target_industries=_strings("target_industries", DEFAULT_TARGET_INDUSTRIES),
        target_countries=_strings("target_countries", DEFAULT_TARGET_COUNTRIES),
        size_band=size_band,
    )


def default_config_payload() -> dict[str, Any]:
    """The shape the settings endpoint returns and accepts."""
    return {
        "weights": dict(DEFAULT_WEIGHTS),
        "target_industries": list(DEFAULT_TARGET_INDUSTRIES),
        "target_countries": list(DEFAULT_TARGET_COUNTRIES),
        "size_band": list(DEFAULT_SIZE_BAND),
    }


__all__ = [
    "DECISION_MAKER_TOKENS",
    "DEFAULT_TARGET_COUNTRIES",
    "DEFAULT_TARGET_INDUSTRIES",
    "DEFAULT_SIZE_BAND",
    "DEFAULT_WEIGHTS",
    "FREE_EMAIL_DOMAINS",
    "FIT_WEIGHT",
    "SETTINGS_KEY",
    "RuleOutcome",
    "ScoreResult",
    "ScoringConfig",
    "build_config",
    "default_config_payload",
    "is_decision_maker",
    "is_free_email",
    "score_breakdown_or_empty",
    "score_lead",
    "split_scores",
    "summarise",
]
