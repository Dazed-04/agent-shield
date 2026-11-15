"""Heuristic inbound / indirect prompt-injection scanner.

Design notes
* Text is normalised (NFKC, zero-width removal, case-folding, leetspeak) and base64 blobs are
  decoded, so trivial obfuscation does not defeat the signatures.
* Signatures are grouped into *categories*. The score is the strongest category, plus a small
  bonus per additional independent category (a credential request *and* an authority claim is
  worse than either alone).
* Some signatures only apply to *untrusted* content (tool output, RAG documents, attachments):
  imperative text addressed to "the AI" is normal in a user prompt but is an attack in a web page.
* All gaps are bounded (``{0,N}``) so scanning stays linear and immune to ReDoS.
"""

import base64
import binascii
import re
import unicodedata
from typing import Any, NamedTuple

MAX_SCAN_CHARS = 60_000


class Signature(NamedTuple):
    category: str
    pattern: re.Pattern[str]
    score: float
    reason: str
    untrusted_only: bool = False
    downgrade_on_benign_cue: bool = False


def _sig(
    category: str,
    pattern: str,
    score: float,
    reason: str,
    untrusted_only: bool = False,
    downgrade_on_benign_cue: bool = False,
) -> Signature:
    return Signature(
        category,
        re.compile(pattern, re.IGNORECASE),
        score,
        reason,
        untrusted_only,
        downgrade_on_benign_cue,
    )


_VERBS_OVERRIDE = r"(?:ignore|disregard|forget|override|discard|abandon|bypass)"
_INSTR_NOUNS = (
    r"(?:instructions?|directions?|rules?|prompts?|guidelines?|directives?|"
    r"constraints?|programming|restrictions?|guardrails?|safeguards?)"
)
_SECRET_NOUNS = (
    r"(?:api[\s_-]?keys?|\.env\b|passwords?|passwd|credentials?|secret(?:\s+keys?)?|"
    r"access\s+tokens?|auth(?:entication)?\s+tokens?|bearer\s+tokens?|private\s+keys?|"
    r"ssh\s+keys?|(?:your|the\s+server'?s?|the\s+system'?s?)\s+(?:environment\s+variables?|env\s+vars?))"
)
_EXFIL_VERBS = (
    r"(?:send|show|reveal|print|give|share|dump|output|tell|leak|exfiltrate|display|"
    r"provide|email|forward|upload|post|extract|expose|disclose|retrieve|fetch|return)"
)

SIGNATURES: list[Signature] = [
    # -- instruction override ------------------------------------------------------------
    _sig(
        "override",
        rf"\b{_VERBS_OVERRIDE}\b[^.\n]{{0,40}}?\b(?:previous|prior|above|earlier|preceding|all|any|"
        rf"your|system|original|everything|initial|existing)\b[^.\n]{{0,30}}?\b{_INSTR_NOUNS}\b",
        85,
        "System instruction override attempt",
    ),
    _sig(
        "override",
        r"\b(?:forget|ignore|disregard)\s+(?:everything|all)\b[^.\n]{0,30}\b(?:told|said|learned|instructed|know|above|before)\b",
        85,
        "Instruction wipe attempt ('forget everything you were told')",
    ),
    _sig(
        "override",
        r"\b(?:ignor(?:e|ez|a|iere|ar)|oubliez?|olvida|vergiss|ignorieren)\b[^.\n]{0,40}\b(?:instructions?|instrucciones|anweisungen|instruktionen|consignes|directives|instru[cç][oõ]es)\b",
        85,
        "System instruction override attempt (non-English)",
    ),
    _sig(
        "override",
        r"(?:पिछले|सभी|पहले)[^.\n]{0,20}निर्देश[^.\n]{0,25}(?:अनदेखा|नजरअंदाज|भूल)",
        85,
        "System instruction override attempt (Hindi)",
    ),
    _sig("override", r"\bsystem\s*override\b", 85, "System override signature"),
    _sig(
        "override",
        r"\bbypass\b[^.\n]{0,30}\b(?:security|guardrails?|filters?|moderation|safety|restrictions?)\b",
        90,
        "Security filter bypass request",
    ),
    # -- persona / jailbreak -------------------------------------------------------------
    _sig(
        "jailbreak",
        r"\bact\s+as\s+dan\b|\bdo\s+anything\s+now\b|\bdan\s+mode\b",
        95,
        "Known DAN jailbreak signature",
    ),
    _sig(
        "jailbreak",
        r"\byou(?:\s+are|'re|\s+have\s+entered)\s+(?:now\s+)?(?:in\s+)?developer\s+mode\b",
        85,
        "Developer-mode jailbreak vector",
    ),
    _sig(
        "jailbreak",
        r"\b(?:enter|enable|activate|switch\s+to)\s+developer\s+mode\b",
        60,
        "Possible developer-mode jailbreak request",
    ),
    _sig(
        "jailbreak",
        r"\b(?:you\s+are\s+now|from\s+now\s+on\s*,?\s+you|pretend\s+(?:to\s+be|you\s+are)|act\s+as\s+(?:if\s+you|an?\s+(?:unrestricted|uncensored|unfiltered)))\b[^.\n]{0,60}\b(?:no|without|free\s+of|zero|unrestricted|uncensored|unfiltered|unbound)\b[^.\n]{0,20}\b(?:restrictions?|limit(?:s|ations)?|filters?|rules?|censorship|guardrails?|ethic\w*|moral\w*)?",
        80,
        "Persona override removing safety restrictions",
    ),
    _sig(
        "jailbreak",
        r"\b(?:ai|assistant|model|chatbot|you)\b[^.\n]{0,20}\b(?:with|having)\s+(?:no|zero)\s+(?:restrictions?|limitations?|filters?|rules?|guardrails?)\b",
        70,
        "Request for an unrestricted AI persona",
    ),
    # -- chat-template / role spoofing ---------------------------------------------------
    _sig(
        "spoofing",
        r"<\|?\s*(?:im_start|im_end|system|endoftext|eot_id|start_header_id)\s*\|?>|\[/?(?:inst|sys)\]|<<\s*/?sys\s*>>",
        80,
        "Chat-template / control-token spoofing",
    ),
    _sig(
        "spoofing",
        r"(?:^|\n)\s*(?:system|assistant|developer)\s*[:>]\s*\S",
        55,
        "Role-label spoofing at line start",
    ),
    # -- prompt exfiltration -------------------------------------------------------------
    _sig(
        "prompt_leak",
        r"\b(?:reveal|print|show|output|repeat|display|leak|tell\s+me|what\s+(?:is|are))\b[^.\n]{0,30}\b(?:system\s+prompt|base\s+prompt|initial\s+prompt|hidden\s+(?:rules|instructions|prompt)|your\s+(?:instructions|rules|guidelines|programming|prompt))\b",
        78,
        "System prompt exfiltration attempt",
    ),
    _sig(
        "prompt_leak",
        r"\brepeat\s+(?:the\s+)?(?:words|text|everything)\s+above\b",
        75,
        "System prompt exfiltration attempt ('repeat the words above')",
    ),
    # -- credential exfiltration / social engineering ------------------------------------
    _sig(
        "credential_exfil",
        rf"\b{_EXFIL_VERBS}\b[^.\n]{{0,50}}?\b{_SECRET_NOUNS}",
        85,
        "Credential or secret exfiltration request",
        downgrade_on_benign_cue=True,
    ),
    _sig(
        "credential_exfil",
        r"\b(?:cat|type|less|more|head|tail|source)\s+\S*\.env\b|\b(?:/etc/(?:passwd|shadow)|id_rsa)\b",
        85,
        "Access to sensitive credential file",
    ),
    _sig(
        "impersonation",
        r"\b(?:i\s*(?:am|'m)|this\s+is|as)\s+(?:the\s+|your\s+|an?\s+)?(?:system\s+admin(?:istrator)?|administrator|sysadmin|root\s+user|security\s+(?:auditor|team|officer)|your\s+(?:creator|developer|owner)|(?:an?\s+)?(?:anthropic|openai|google)\s+(?:employee|engineer|staff))\b",
        45,
        "Authority impersonation / social-engineering vector",
    ),
    # -- destructive payloads ------------------------------------------------------------
    _sig(
        "destructive",
        r"\b(?:drop\s+table|delete\s+from|truncate\s+table|rm\s+-[a-z]*r[a-z]*f|mkfs\b|format\s+c:)",
        60,
        "Destructive system payload in prompt",
    ),
    # -- exfiltration channels ----------------------------------------------------------
    _sig(
        "exfil_channel",
        r"!\[[^\]]*\]\(\s*https?://[^)\s]*[?&][^)\s]*=",
        70,
        "Markdown image data-exfiltration beacon",
    ),
    # -- indirect-injection (untrusted content only) --------------------------------------
    _sig(
        "indirect",
        r"\b(?:send|forward|email|post|upload|transmit|exfiltrate)\b[^.\n]{0,60}\b(?:to|at)\s+(?:\S+@\S+|https?://\S+)",
        78,
        "Embedded instruction to transmit data to an external destination",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"\b(?:important|urgent|attention|note)\b[^.\n]{0,15}\b(?:to|for)\s+(?:the\s+)?(?:ai|assistant|llm|model|agent|chatbot)\b",
        80,
        "Content addressed to the AI agent",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"\b(?:ai|assistant|llm|agent)\s*[:,]\s*(?:please\s+)?(?:you\s+(?:must|should|will)|ignore|forget|do\s+not|don'?t|send|execute|run|delete|reveal)",
        80,
        "Embedded imperative directed at the AI agent",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"\bdo\s+not\s+(?:tell|inform|mention|reveal|alert)\b[^.\n]{0,30}\b(?:user|human|operator|anyone)\b",
        80,
        "Instruction to conceal actions from the user",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"\b(?:new|updated|additional)\s+(?:instructions?|task|objective|directive)s?\s*:",
        70,
        "Embedded 'new instructions' block",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"\bwhen(?:ever)?\s+(?:you\s+)?(?:read|see|process|summari[sz]e|parse)\s+this\b",
        70,
        "Trigger phrase aimed at the reading agent",
        untrusted_only=True,
    ),
    _sig(
        "indirect",
        r"<!--[^>]{0,400}?\b(?:ignore|system|instruction|assistant|execute|send)\b[^>]{0,400}?-->",
        75,
        "Instruction hidden in an HTML comment",
        untrusted_only=True,
    ),
]

_BENIGN_CUES = re.compile(
    r"\b(?:example|sample|dummy|fake|placeholder|format|rotate|rotation|generate|store|"
    r"storing|manage|managing|best\s+practices?|what\s+is|how\s+(?:do|to|can|should)|"
    r"explain|policy|policies|secure|safely|protect)\b",
    re.IGNORECASE,
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"), None)
_LEET_MAP = str.maketrans("013457@$", "oieastas")
_LEET_TOKEN = re.compile(r"\b(?=[a-z0-9@$]*[a-z])(?=[a-z0-9@$]*[0-9@$])[a-z0-9@$]{4,}\b")
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return re.sub(r"[ \t\r\f\v]+", " ", text).lower()


def _deleet(text: str) -> str:
    return _LEET_TOKEN.sub(lambda m: m.group(0).translate(_LEET_MAP), text)


def _decode_base64_blobs(text: str, limit: int = 5) -> list[str]:
    decoded: list[str] = []
    for blob in _B64_BLOB.findall(text)[:limit]:
        try:
            raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
            candidate = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        printable = sum(ch.isprintable() or ch.isspace() for ch in candidate)
        if candidate and printable / len(candidate) >= 0.9:
            decoded.append(normalise(candidate))
    return decoded


class PromptScanner:
    """Scans prompts and untrusted content for injection signatures."""

    signatures = SIGNATURES

    def _scan_text(self, text: str, untrusted: bool) -> list[tuple[Signature, float, str]]:
        text = text[:MAX_SCAN_CHARS]
        base = normalise(text)
        variants = [("", base)]
        deleeted = _deleet(base)
        if deleeted != base:
            variants.append(("obfuscated (leetspeak)", deleeted))
        variants += [("obfuscated (base64)", d) for d in _decode_base64_blobs(text)]

        hits: list[tuple[Signature, float, str]] = []
        for tag, variant in variants:
            for sig in self.signatures:
                if sig.untrusted_only and not untrusted:
                    continue
                m = sig.pattern.search(variant)
                if not m:
                    continue
                score = sig.score
                if sig.downgrade_on_benign_cue and _BENIGN_CUES.search(variant):
                    score = min(score, 40.0)
                hits.append((sig, score, tag))
        return hits

    @staticmethod
    def _summarise(hits: list[tuple[Signature, float, str]], source: str) -> dict[str, Any]:
        if not hits:
            return {
                "score": 0.0,
                "flagged": False,
                "reasons": ["No malicious injection patterns identified."],
                "categories": [],
            }
        best_per_cat: dict[str, tuple[float, str]] = {}
        obfuscated = False
        for sig, score, tag in hits:
            reason = sig.reason + (f" [{tag}]" if tag else "")
            obfuscated = obfuscated or bool(tag)
            if sig.category not in best_per_cat or score > best_per_cat[sig.category][0]:
                best_per_cat[sig.category] = (score, reason)

        ordered = sorted(best_per_cat.items(), key=lambda kv: kv[1][0], reverse=True)
        top = ordered[0][1][0]
        # A single strong category is already decisive; independent categories add confidence.
        bonus = 5.0 * (len(ordered) - 1) + (5.0 if obfuscated else 0.0)
        score = min(100.0, top + bonus)
        return {
            "score": round(score, 2),
            "flagged": score >= 50.0,
            "reasons": [f"{r}" for _, (_, r) in ordered],
            "categories": [c for c, _ in ordered],
            "source": source,
        }

    def scan(self, prompt: str, retrieved_context: str | None = None) -> dict[str, Any]:
        """Scan a user prompt (trusted channel) plus any retrieved / attached content (untrusted)."""
        hits = self._scan_text(prompt or "", untrusted=False)
        source = "prompt"
        if retrieved_context:
            ctx_hits = self._scan_text(retrieved_context, untrusted=True)
            if ctx_hits:
                source = "prompt+retrieved_context" if hits else "retrieved_context"
            hits += ctx_hits
        return self._summarise(hits, source)

    def scan_untrusted(self, text: str, source: str = "untrusted") -> dict[str, Any]:
        """Scan tool output / web / RAG content on its way *back* to the model."""
        return self._summarise(self._scan_text(text or "", untrusted=True), source)
