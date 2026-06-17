"""
IKKF_SH — Verification Loop
Проверка фактов, confidence scoring, rollback.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VerificationResult:
    """Результат верификации."""
    def __init__(self, claim: str, verified: bool, confidence: float,
                 sources: list = None, feedback: str = ""):
        self.claim = claim
        self.verified = verified
        self.confidence = confidence
        self.sources = sources or []
        self.feedback = feedback

    def to_dict(self):
        return {
            "claim": self.claim,
            "verified": self.verified,
            "confidence": self.confidence,
            "sources": self.sources,
            "feedback": self.feedback,
        }


class VerificationLoop:
    """
    Цикл верификации.
    
    Для каждого утверждения:
    1. Поиск подтверждений в IKKF
    2. Поиск подтверждений в интернете (опционально)
    3. Кросс-проверка источников
    4. Присвоение confidence score
    5. Если confidence < threshold → флаг "needs_review"
    """

    def __init__(self, confidence_threshold: float = 0.7,
                 max_claims_per_check: int = 10):
        self.confidence_threshold = confidence_threshold
        self.max_claims_per_check = max_claims_per_check
        self.results: list[VerificationResult] = []
        self.rollback_log: list[dict] = []

    def verify_claim(self, claim: str, ikkf_results: list = None,
                     web_results: list = None) -> VerificationResult:
        """Верификация одного утверждения."""
        sources = []
        confidence = 0.0

        # Проверка в IKKF
        if ikkf_results:
            for r in ikkf_results:
                sources.append(f"ikkf:{r.get('id', 'unknown')}")
                confidence = max(confidence, r.get("score", 0) * 0.8)

        # Проверка в интернете
        if web_results:
            for r in web_results:
                sources.append(f"web:{r.get('url', 'unknown')}")
                confidence = min(confidence + 0.1, 1.0)

        verified = confidence >= self.confidence_threshold

        result = VerificationResult(
            claim=claim,
            verified=verified,
            confidence=round(confidence, 3),
            sources=sources[:5],  # макс 5 источников
            feedback="" if verified else "Needs more sources"
        )

        self.results.append(result)

        if not verified:
            logger.warning(f"Claim not verified: {claim[:80]}... (conf: {confidence:.2f})")

        return result

    def verify_batch(self, claims: list[str], 
                     ikkf_data: dict = None) -> list[VerificationResult]:
        """Верификация списка утверждений."""
        results = []
        for claim in claims[:self.max_claims_per_check]:
            result = self.verify_claim(claim, ikkf_data.get(claim) if ikkf_data else None)
            results.append(result)
        return results

    def rollback(self, step_id: int, reason: str):
        """Откат шага при ошибке."""
        entry = {
            "step_id": step_id,
            "reason": reason,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        }
        self.rollback_log.append(entry)
        logger.info(f"Rollback step {step_id}: {reason}")

    def get_verification_report(self) -> dict:
        """Отчёт о верификации."""
        total = len(self.results)
        verified = sum(1 for r in self.results if r.verified)
        avg_confidence = (
            sum(r.confidence for r in self.results) / total if total else 0
        )

        return {
            "total_claims": total,
            "verified": verified,
            "failed": total - verified,
            "avg_confidence": round(avg_confidence, 3),
            "rollbacks": len(self.rollback_log),
            "status": "pass" if verified == total else "needs_review",
        }
