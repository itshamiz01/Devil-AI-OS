"""Legal / platform / ethical screening (P-03 §15).

Deterministic keyword screening over an opportunity's own declared fields
(name, description, problem, solution, revenue model, category). This is a
screen, not legal advice: high-risk flags mark where professional review
is required; prohibited matches are hard rejections that override any
score (§16.4). Screening never *approves* legality — a clean screen only
means "no prohibited pattern matched".
"""
from __future__ import annotations

import re

# rule_id -> (patterns, human-readable basis). Patterns match the
# opportunity's declared text, case-insensitively.
PROHIBITED_RULES: list[tuple[str, list[str], str]] = [
    ("fraud", [r"\bfraud\b", r"\bscam\b", r"fake (invoice|receipt|document)"],
     "Fraud is a prohibited category (§15)."),
    ("phishing", [r"\bphishing\b", r"fake login page", r"clone .* login"],
     "Phishing is a prohibited category (§15)."),
    ("credential_theft", [r"credential (theft|stealing|harvest)", r"steal .*password", r"password stealer"],
     "Credential theft is a prohibited category (§15)."),
    ("malware", [r"\bmalware\b", r"\bransomware\b", r"\bspyware\b", r"\bkeylogger\b"],
     "Malware is a prohibited category (§15)."),
    ("unauthorized_access", [r"unauthorized access", r"hack into", r"bypass .*security control"],
     "Unauthorized access is a prohibited category (§15)."),
    ("fake_reviews", [r"fake review", r"paid review(s)? (service|writing|posting)", r"review manipulation",
                      r"astroturf"],
     "Fake reviews / review manipulation are prohibited (§14, §15)."),
    ("spam_operations", [r"\bspam\b", r"bulk unsolicited", r"cold (email|message) blast",
                         r"mass unsolicited"],
     "Spam operations and unsolicited bulk messaging are prohibited (§14, §15)."),
    ("counterfeit", [r"\bcounterfeit\b", r"replica (brand|designer|luxury)", r"fake branded"],
     "Counterfeit goods are prohibited (§15)."),
    ("copyright_infringement", [r"pirated", r"cracked (software|app|game)", r"torrent .*premium",
                                r"stolen content", r"plagiaris"],
     "Copyright infringement is a prohibited category (§15)."),
    ("deceptive_advertising", [r"guaranteed income", r"get rich quick", r"guaranteed profit",
                               r"risk[- ]free income", r"double your money"],
     "Deceptive advertising / guaranteed-income claims are prohibited (§15)."),
    ("unauthorized_data_harvesting", [r"harvest .*personal data", r"scrape .*emails", r"scraping personal",
                                      r"sell .*personal data", r"email list scraping"],
     "Unauthorized data harvesting is prohibited (§15)."),
    ("market_manipulation", [r"pump and dump", r"market manipulation", r"wash trading"],
     "Market manipulation is a prohibited category (§15)."),
    ("illegal_financial_schemes", [r"\bponzi\b", r"pyramid scheme", r"guaranteed returns",
                                   r"unlicensed (lending|investment)"],
     "Illegal financial schemes are prohibited (§15)."),
    ("misleading_medical_claims", [r"miracle cure", r"cure(s)? (diabetes|cancer|aids)",
                                   r"guaranteed weight loss"],
     "Misleading medical claims are a prohibited category (§15)."),
    ("platform_circumvention", [r"circumvent .*platform", r"bypass .*(paywall|captcha|rate limit)",
                                r"evade .*detection"],
     "Circumvention of platform protections is prohibited (§15)."),
]

# Categories that are not prohibited but require professional review and
# extra scrutiny (§15). Flagging caps recommendation until reviewed.
HIGH_RISK_RULES: list[tuple[str, list[str], str]] = [
    ("financial_advice", [r"financial advice", r"investment advice", r"trading signals",
                          r"stock tips", r"portfolio management"],
     "Financial advice is a regulated activity in most jurisdictions."),
    ("medical_health_claims", [r"health claim", r"treatment", r"diagnos", r"supplement",
                               r"weight loss", r"fitness program"],
     "Health-related claims require substantiation and may be regulated."),
    ("legal_services", [r"legal advice", r"legal services", r"contract drafting service"],
     "Legal services may require professional licensing."),
    ("personal_data_processing", [r"personal data", r"customer data", r"patient", r"clinic",
                                  r"health records", r"children'?s data"],
     "Processing personal data triggers privacy obligations (e.g. India's DPDP Act, GDPR)."),
    ("children_products", [r"\bkids\b", r"\bchildren\b", r"child", r"minors"],
     "Products for children carry additional safety and privacy rules."),
    ("professional_certification", [r"certification prep", r"exam preparation", r"licensed professional"],
     "Certification-related offerings may be restricted by the certifying body."),
]


def _haystack(opportunity) -> str:
    parts = [
        getattr(opportunity, "name", "") or "",
        getattr(opportunity, "description", "") or "",
        getattr(opportunity, "problem_statement", "") or "",
        getattr(opportunity, "proposed_solution", "") or "",
        getattr(opportunity, "revenue_model", "") or "",
        getattr(opportunity, "category", "") or "",
    ]
    return " \n ".join(parts).lower()


def screen(opportunity) -> dict:
    """Returns {verdict, matched_rules, flags, requires_professional_review}."""
    text = _haystack(opportunity)
    matched: list[dict] = []
    for rule_id, patterns, basis in PROHIBITED_RULES:
        for pattern in patterns:
            if re.search(pattern, text):
                matched.append({"rule": rule_id, "pattern": pattern, "basis": basis})
                break
    flags: list[dict] = []
    for flag_id, patterns, basis in HIGH_RISK_RULES:
        for pattern in patterns:
            if re.search(pattern, text):
                flags.append({"flag": flag_id, "basis": basis})
                break
    verdict = "prohibited" if matched else ("flagged" if flags else "clear")
    return {
        "verdict": verdict,
        "matched_rules": matched,
        "flags": flags,
        "requires_professional_review": bool(flags),
        "note": ("Screening is a deterministic pattern check over declared fields; "
                 "a 'clear' verdict is not a legal opinion (§15)."),
    }
