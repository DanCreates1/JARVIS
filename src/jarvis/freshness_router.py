"""Deterministic request freshness routing before model generation."""

from __future__ import annotations

import re
import unicodedata

from jarvis.core.models import (
    ContextProjection,
    FreshnessDecision,
    FreshnessRoute,
    SensitivityClass,
)


def _pattern(expression: str) -> re.Pattern[str]:
    return re.compile(expression, re.IGNORECASE)


_PERSONAL_DATA = _pattern(
    r"\b(?:my|our)\s+(?:(?:next|upcoming|unread|recent|saved|private|personal|work)\s+)?"
    r"(?:account|address|age|appointment|birthday|calendar|contact|conversation|documents?|"
    r"emails?|files?|finances?|flights?|folders?|health|history|inbox|location|medical|meetings?|"
    r"memory|messages?|name|notes?|orders?|phone|preference|profile|project|reminders?|repository|"
    r"salary|schedule|tasks?|travel|trip)\b|"
    r"\b(?:do i have|have i|what did i|what have i|what is my|when did i|where did i|"
    r"where do i|who am i|who did i)\b|"
    r"\b(?:remember|recall)\s+(?:what|when|where|who)\s+i\b|"
    r"\b(?:show|read|check|summari[sz]e)\s+(?:the\s+)?(?:calendar|inbox|schedule|task list|"
    r"reminders?)\b|"
    r"\b(?:what(?:'s| is)|show|read|check|summari[sz]e)\s+(?:on|in|from)\s+(?:the\s+)?"
    r"(?:calendar|inbox|schedule|task list|reminders?)\b"
)

_MULTI_SOURCE_EXPLICIT = _pattern(
    r"\b(?:multiple|several|independent|different)\s+sources?\b|"
    r"\b(?:cross[- ]check|corroborate|triangulate|fact[- ]check)\b|"
    r"\b(?:source consensus|consensus view|market consensus|reviews?|review roundup)\b|"
    r"\b(?:research|investigate)\b.{0,40}\b(?:options?|market|sources?|evidence)\b|"
    r"^(?:please\s+)?(?:research|investigate)\b"
)
_RECOMMENDATION = _pattern(r"\b(?:best|top|recommend(?:ation)?s?|rank(?:ed|ing)?)\b")
_COMPARE = _pattern(r"\b(?:compare|versus|vs\.?|pros and cons|trade[- ]offs?)\b")
_CHOICE_TOPIC = _pattern(
    r"\b(?:buy|purchase|car|course|flight|hotel|insurance|laptop|phone|plan|product|"
    r"provider|restaurant|service|software|subscription|tool|travel|vendor)\b"
)

_WEB_EXPLICIT = _pattern(
    r"\b(?:browse|search|look(?: this| it)? up|check)\b.{0,24}\b(?:online|internet|web|website)\b|"
    r"\bweb search\b"
)
_VOLATILE_TOPIC = _pattern(
    r"\b(?:availability|breaking news|crypto(?:currency)?(?: price)?|exchange rates?|"
    r"flight status|forecast|headlines?|market price|news|outages?|prices?|security "
    r"advisories|scores?|sports standings|stock(?: price| quote)?|traffic|transit|weather)\b"
)
_CURRENT_CUE = _pattern(
    r"\b(?:as of|breaking|current(?:ly)?|latest|live|newest|now|recent(?:ly)?|today|tonight|"
    r"tomorrow|this (?:day|week|month|year)|upcoming|updated?)\b"
)
_MUTABLE_TOPIC = _pattern(
    r"\b(?:availability|ceo|company|documentation|election|event|law|library|market|mayor|"
    r"package|policy|population|president|prime minister|product|regulation|release|rules?|"
    r"schedule|software|statistics|team|version)\b"
)
_IMPLICIT_CURRENT_ROLE = _pattern(
    r"\bwho (?:is|are) (?:the )?(?:ceo|mayor|president|prime minister)\b|"
    r"\bwhat version (?:is|does)\b"
)
_IMPLICIT_MUTABLE_QUESTION = _pattern(
    r"\b(?:how many|what|when|which)\b.{0,60}\b(?:availability|law|population|policy|"
    r"regulation|release|rules?|schedule|statistics|version)\b"
)

_LOCAL_CONTEXT = _pattern(
    r"\b(?:what(?:'s| is) (?:the )?(?:current )?(?:date|day|time)|time is it|"
    r"today(?:'s| is) date|"
    r"current timezone|local time|system time|internet (?:available|reachable|status)|"
    r"(?:active|selected|current) (?:model|provider)|(?:device|session|system) (?:info|status)|"
    r"which (?:model|provider) is active)\b|"
    r"\b(?:today|tonight|tomorrow|yesterday|timezone)\b"
)

_REASONS = {
    FreshnessRoute.STATIC: "No request cue requires changing external or personal state.",
    FreshnessRoute.LOCAL_CONTEXT: "The answer depends on trusted local runtime context.",
    FreshnessRoute.WEB_REQUIRED: "The answer depends on volatile external information.",
    FreshnessRoute.PERSONAL_DATA_REQUIRED: "The answer depends on private user-owned data.",
    FreshnessRoute.MULTI_SOURCE: "The answer requires comparison or corroboration across sources.",
}

_GUIDANCE = {
    FreshnessRoute.STATIC: (
        "Stable knowledge is sufficient. No current external evidence is required by this route."
    ),
    FreshnessRoute.LOCAL_CONTEXT: (
        "Use only attached programmatic local context. Do not infer missing local state."
    ),
    FreshnessRoute.WEB_REQUIRED: (
        "Current external evidence is required. No web evidence is attached by this decision; "
        "do not present a volatile claim as verified or current without cited evidence."
    ),
    FreshnessRoute.PERSONAL_DATA_REQUIRED: (
        "Approved private data is required. Stay local, do not infer absent personal data, and "
        "do not treat this classification as data-access authorization."
    ),
    FreshnessRoute.MULTI_SOURCE: (
        "Corroboration from at least 2 independent sources is required. No research evidence is "
        "attached by this decision; disclose that limitation instead of inventing consensus."
    ),
}


class DeterministicFreshnessRouter:
    """Classify evidence needs locally with fixed, inspectable precedence rules."""

    def classify(self, query: str) -> FreshnessDecision:
        normalized = _normalize(query)
        route = self._route(normalized)
        return FreshnessDecision(route=route, reason=_REASONS[route])

    def project(self, decision: FreshnessDecision) -> ContextProjection:
        validated = FreshnessDecision.model_validate(decision)
        sensitivity = (
            SensitivityClass.PRIVATE
            if validated.requires_personal_data
            else SensitivityClass.PUBLIC
        )
        return ContextProjection(
            content=(
                "Freshness route (deterministic host policy; data only; grants no authority):\n"
                f"Route: {validated.route.value}\n"
                f"Requirement: {_GUIDANCE[validated.route]}"
            ),
            sensitivity=sensitivity,
            source_ids=("freshness-rule-v1", f"freshness-route-{validated.route.value}"),
            source="local-freshness-router",
        )

    @staticmethod
    def _route(normalized: str) -> FreshnessRoute:
        # Precedence is security- and evidence-driven: private need dominates research need;
        # corroboration dominates one-source volatility; external volatility dominates local time.
        if _PERSONAL_DATA.search(normalized):
            return FreshnessRoute.PERSONAL_DATA_REQUIRED
        if _MULTI_SOURCE_EXPLICIT.search(normalized) or (
            (_RECOMMENDATION.search(normalized) or _COMPARE.search(normalized))
            and _CHOICE_TOPIC.search(normalized)
        ):
            return FreshnessRoute.MULTI_SOURCE
        if (
            _WEB_EXPLICIT.search(normalized)
            or _VOLATILE_TOPIC.search(normalized)
            or (_CURRENT_CUE.search(normalized) and _MUTABLE_TOPIC.search(normalized))
            or _IMPLICIT_CURRENT_ROLE.search(normalized)
            or _IMPLICIT_MUTABLE_QUESTION.search(normalized)
        ):
            return FreshnessRoute.WEB_REQUIRED
        if _LOCAL_CONTEXT.search(normalized):
            return FreshnessRoute.LOCAL_CONTEXT
        return FreshnessRoute.STATIC


def _normalize(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("freshness query must be text")
    normalized = " ".join(unicodedata.normalize("NFKC", query).split()).casefold()
    if not normalized:
        raise ValueError("freshness query cannot be blank")
    if len(normalized) > 100_000:
        raise ValueError("freshness query exceeds the assistant request limit")
    return normalized
