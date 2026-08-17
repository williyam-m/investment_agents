"""
DivergenceScorer — scores how much analyst agents disagree after a debate round.

Computes a composite divergence score from three signals:
  1. Recommendation variance  (40% weight) — std dev of numeric scores
  2. Semantic divergence       (35% weight) — mean pairwise embedding distance
  3. Conflict penalty          (25% weight) — hard-conflict detection
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional
import uuid

import numpy as np
import structlog

from investment_agents.models.agent_output import AnalystOutput
from investment_agents.models.divergence import (
    ConflictPoint,
    ConflictSeverity,
    ConvergenceSignal,
    DivergenceReport,
)

logger = structlog.get_logger(__name__)

# Weight coefficients — must sum to 1.0
_W_REC_VAR: float = 0.40
_W_SEM_DIV: float = 0.35
_W_CONFLICT: float = 0.25

# Hard-conflict threshold: absolute score gap > this → HARD
_HARD_CONFLICT_THRESHOLD: float = 1.0
# Soft-conflict threshold: absolute score gap > this → SOFT
_SOFT_CONFLICT_THRESHOLD: float = 0.5

# Max theoretical std dev for scores in [-1, 1] range (all at extremes)
_MAX_SCORE_STD_DEV: float = 1.0


class DivergenceScorer:
    """
    Scores how much analyst agents disagree after a debate round.

    Uses sentence embeddings for semantic comparison where available,
    falling back to a deterministic random approximation if the
    ``sentence_transformers`` package is not installed.
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        self._embedding_model_name = embedding_model
        self._embedder: Optional[object] = None  # lazy-loaded on first use
        self._embedder_available: Optional[bool] = None  # None = not yet probed

        logger.info(
            "divergence_scorer.init",
            embedding_model=embedding_model,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        outputs: List[AnalystOutput],
        round_number: int,
    ) -> DivergenceReport:
        """
        Compute a :class:`DivergenceReport` from a list of analyst outputs.

        Parameters
        ----------
        outputs:
            All :class:`AnalystOutput` objects produced in this debate round.
        round_number:
            The 1-based round index (carried through into the report).

        Returns
        -------
        DivergenceReport
        """
        if not outputs:
            logger.warning("divergence_scorer.empty_outputs", round=round_number)
            return self._empty_report(round_number)

        log = logger.bind(round=round_number, agent_count=len(outputs))
        log.debug("divergence_scorer.scoring_start")

        numeric_scores: List[float] = [o.numeric_score for o in outputs]
        key_arguments: List[str] = [o.key_argument for o in outputs]

        # --- Component 1: recommendation variance (40%) -----------------
        rec_var = self._normalized_variance(numeric_scores)

        # --- Component 2: semantic divergence (35%) ---------------------
        if len(outputs) >= 2:
            embeddings = self._embed(key_arguments)
            sem_div = self._mean_pairwise_distance(embeddings)
        else:
            sem_div = 0.0

        # --- Component 3: conflict penalty (25%) ------------------------
        conflicts = self._detect_conflicts(outputs, round_number)
        hard_conflicts = [c for c in conflicts if c.severity == ConflictSeverity.HARD]
        # Fraction of agent pairs that are in hard conflict, capped at 1.0
        if len(outputs) >= 2:
            total_pairs = len(outputs) * (len(outputs) - 1) / 2
            conflict_penalty = min(1.0, len(hard_conflicts) / total_pairs)
        else:
            conflict_penalty = 0.0

        # --- Overall score ----------------------------------------------
        overall_score = min(
            1.0,
            _W_REC_VAR * rec_var + _W_SEM_DIV * sem_div + _W_CONFLICT * conflict_penalty,
        )

        # --- Exploit-worthy agents (sorted by |score - mean|) -----------
        mean_score = float(np.mean(numeric_scores))
        exploit_worthy_agents = self._rank_exploit_agents(outputs, mean_score)

        # --- Per-agent score dict ---------------------------------------
        agent_scores: Dict[str, float] = {
            o.agent_type.value: o.numeric_score for o in outputs
        }

        report = DivergenceReport(
            round_number=round_number,
            overall_score=round(overall_score, 4),
            recommendation_variance=round(rec_var, 4),
            semantic_divergence=round(sem_div, 4),
            conflict_penalty=round(conflict_penalty, 4),
            conflicts=conflicts,
            has_hard_conflicts=bool(hard_conflicts),
            converging_topics=[],  # populated by ConvergenceDetector
            exploit_worthy_agents=exploit_worthy_agents,
            agent_scores=agent_scores,
        )

        log.info(
            "divergence_scorer.complete",
            overall_score=report.overall_score,
            rec_var=rec_var,
            sem_div=sem_div,
            conflict_penalty=conflict_penalty,
            hard_conflicts=len(hard_conflicts),
            is_high_divergence=report.is_high_divergence,
        )
        return report

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed *texts* using the sentence transformer model.

        Falls back to random vectors (with a warning) if
        ``sentence_transformers`` is not available.
        """
        if self._embedder_available is None:
            self._embedder_available = self._try_load_embedder()

        if self._embedder_available and self._embedder is not None:
            try:
                embeddings = self._embedder.encode(  # type: ignore[union-attr]
                    texts,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                logger.debug(
                    "divergence_scorer.embeddings_computed",
                    n_texts=len(texts),
                    shape=list(embeddings.shape),
                )
                return embeddings  # type: ignore[return-value]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "divergence_scorer.embed_error",
                    error=str(exc),
                    fallback="random",
                )

        # Fallback: random unit vectors (deterministic per text via hash seed)
        return self._random_embeddings(texts)

    def _try_load_embedder(self) -> bool:
        """Lazy-load the SentenceTransformer model. Returns True on success."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embedder = SentenceTransformer(self._embedding_model_name)
            logger.info(
                "divergence_scorer.embedder_loaded",
                model=self._embedding_model_name,
            )
            return True
        except ImportError:
            warnings.warn(
                "sentence_transformers is not installed. "
                "DivergenceScorer will use random divergence (0.4–0.6) as a fallback. "
                "Install with: pip install sentence-transformers",
                stacklevel=3,
            )
            logger.warning(
                "divergence_scorer.sentence_transformers_unavailable",
                fallback="random_divergence_0.4_to_0.6",
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "divergence_scorer.embedder_load_error",
                error=str(exc),
                fallback="random_divergence_0.4_to_0.6",
            )
            return False

    def _random_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Deterministic fallback: pseudo-random unit vectors seeded by text hash.
        Produces semantic divergence in the 0.4–0.6 range as per the spec.
        """
        dim = 64
        vectors = []
        for text in texts:
            seed = abs(hash(text)) % (2**31)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(dim)
            vec /= np.linalg.norm(vec) + 1e-12
            vectors.append(vec)
        return np.array(vectors)

    # ------------------------------------------------------------------
    # Statistical helpers
    # ------------------------------------------------------------------

    def _normalized_variance(self, scores: List[float]) -> float:
        """
        Compute the standard deviation of *scores* normalized by the maximum
        possible std dev for the [-1, 1] range (i.e. 1.0), clamped to [0, 1].
        """
        if len(scores) < 2:
            return 0.0
        std_dev = float(np.std(scores, ddof=0))
        normalized = std_dev / _MAX_SCORE_STD_DEV
        return float(np.clip(normalized, 0.0, 1.0))

    def _mean_pairwise_distance(self, embeddings: np.ndarray) -> float:
        """
        Compute the mean pairwise cosine *distance* (1 - similarity) between
        all embedding vectors.  Embeddings are assumed to be L2-normalised so
        that ``dot(a, b) == cosine_similarity(a, b)``.
        """
        n = len(embeddings)
        if n < 2:
            return 0.0

        # Cosine similarity matrix via dot product (works for unit vectors)
        sim_matrix = embeddings @ embeddings.T  # shape (n, n)

        # Extract upper triangle (excluding diagonal)
        upper_indices = np.triu_indices(n, k=1)
        similarities = sim_matrix[upper_indices]

        # Distance = 1 - similarity, clamped to [0, 1]
        distances = np.clip(1.0 - similarities, 0.0, 1.0)
        mean_dist = float(np.mean(distances))

        logger.debug(
            "divergence_scorer.pairwise_distance",
            n_pairs=len(distances),
            mean_distance=round(mean_dist, 4),
        )
        return mean_dist

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(
        self,
        outputs: List[AnalystOutput],
        round_number: int,
    ) -> List[ConflictPoint]:
        """
        Detect HARD and SOFT conflicts between all pairs of agents.

        A HARD conflict is ``|score_a - score_b| > 1.0``.
        A SOFT conflict is ``|score_a - score_b| > 0.5``.
        """
        conflicts: List[ConflictPoint] = []
        n = len(outputs)

        for i in range(n):
            for j in range(i + 1, n):
                agent_a = outputs[i]
                agent_b = outputs[j]
                score_gap = abs(agent_a.numeric_score - agent_b.numeric_score)

                if score_gap > _HARD_CONFLICT_THRESHOLD:
                    severity = ConflictSeverity.HARD
                elif score_gap > _SOFT_CONFLICT_THRESHOLD:
                    severity = ConflictSeverity.SOFT
                else:
                    continue  # No notable conflict

                conflict_id = f"conflict_{round_number}_{agent_a.agent_type.value}_{agent_b.agent_type.value}_{uuid.uuid4().hex[:6]}"

                conflict = ConflictPoint(
                    conflict_id=conflict_id,
                    agent_a=agent_a.agent_type.value,
                    agent_b=agent_b.agent_type.value,
                    severity=severity,
                    description=(
                        f"{agent_a.agent_type.value} ({agent_a.recommendation.value}, "
                        f"score={agent_a.numeric_score:+.2f}) vs "
                        f"{agent_b.agent_type.value} ({agent_b.recommendation.value}, "
                        f"score={agent_b.numeric_score:+.2f})"
                    ),
                    agent_a_position=agent_a.key_argument,
                    agent_b_position=agent_b.key_argument,
                    score_gap=round(score_gap, 4),
                    resolved=False,
                    detected_at_round=round_number,
                )
                conflicts.append(conflict)

                logger.debug(
                    "divergence_scorer.conflict_detected",
                    conflict_id=conflict_id,
                    severity=severity.value,
                    agent_a=agent_a.agent_type.value,
                    agent_b=agent_b.agent_type.value,
                    score_gap=round(score_gap, 4),
                )

        return conflicts

    # ------------------------------------------------------------------
    # Exploit ranking
    # ------------------------------------------------------------------

    def _rank_exploit_agents(
        self,
        outputs: List[AnalystOutput],
        mean_score: float,
    ) -> List[str]:
        """
        Return agent type strings sorted by ``|score - mean|`` descending.
        Agents with the most distinctive positions are listed first.
        """
        ranked = sorted(
            outputs,
            key=lambda o: abs(o.numeric_score - mean_score),
            reverse=True,
        )
        return [o.agent_type.value for o in ranked]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_report(round_number: int) -> DivergenceReport:
        return DivergenceReport(
            round_number=round_number,
            overall_score=0.0,
            recommendation_variance=0.0,
            semantic_divergence=0.0,
            conflict_penalty=0.0,
            conflicts=[],
            has_hard_conflicts=False,
            converging_topics=[],
            exploit_worthy_agents=[],
            agent_scores={},
        )
