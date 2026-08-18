"""
ConvergenceDetector — finds converging topics / themes from analyst outputs.

After a debate round, agents that:
  - have a numeric_score gap < 0.3 (close recommendations), AND
  - share similar key_argument themes (cosine similarity > threshold)

…are considered to be converging on a topic.  The detector groups such
agents and returns a :class:`list[ConvergenceSignal]` that the orchestrator
can use to confirm consensus areas or to skip redundant explore steps.
"""

from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from investment_agents.models.agent_output import AnalystOutput
from investment_agents.models.divergence import ConvergenceSignal

logger = structlog.get_logger(__name__)

# Score gap below which two agents are considered "close"
_SCORE_GAP_THRESHOLD: float = 0.3

# Cosine similarity above which two arguments are considered "similar"
_SEMANTIC_SIMILARITY_THRESHOLD: float = 0.70

# Minimum group size to emit a ConvergenceSignal
_MIN_GROUP_SIZE: int = 2


class ConvergenceDetector:
    """
    Detects convergence signals across analyst outputs.

    Uses sentence embeddings for semantic theme comparison when
    ``sentence_transformers`` is available; falls back to a keyword-overlap
    heuristic otherwise.

    Parameters
    ----------
    embedding_model:
        The ``sentence-transformers`` model name for encoding key_argument
        strings.  Defaults to ``"all-MiniLM-L6-v2"``.
    score_gap_threshold:
        Maximum absolute difference in ``numeric_score`` for two agents to be
        considered "close".  Defaults to 0.3.
    semantic_similarity_threshold:
        Minimum cosine similarity between key_argument embeddings for the
        agents to be considered thematically aligned.  Defaults to 0.70.
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        score_gap_threshold: float = _SCORE_GAP_THRESHOLD,
        semantic_similarity_threshold: float = _SEMANTIC_SIMILARITY_THRESHOLD,
    ) -> None:
        self._embedding_model_name = embedding_model
        self._score_gap_threshold = score_gap_threshold
        self._semantic_threshold = semantic_similarity_threshold
        self._embedder: Optional[object] = None
        self._embedder_available: Optional[bool] = None

        logger.info(
            "convergence_detector.init",
            embedding_model=embedding_model,
            score_gap_threshold=score_gap_threshold,
            semantic_similarity_threshold=semantic_similarity_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        outputs: List[AnalystOutput],
        round_number: int,
    ) -> List[ConvergenceSignal]:
        """
        Identify groups of agents that are converging.

        Parameters
        ----------
        outputs:
            All :class:`AnalystOutput` objects from the current round.
        round_number:
            The 1-based round index (carried into each :class:`ConvergenceSignal`).

        Returns
        -------
        list[ConvergenceSignal]
            One signal per detected convergence cluster, or an empty list if
            no convergence is found.
        """
        if len(outputs) < _MIN_GROUP_SIZE:
            logger.debug("convergence_detector.insufficient_agents", count=len(outputs))
            return []

        log = logger.bind(round=round_number, agent_count=len(outputs))
        log.debug("convergence_detector.start")

        # Step 1 — embed all key_arguments
        texts = [o.key_argument for o in outputs]
        embeddings = self._embed(texts)  # shape (n, dim)

        # Step 2 — build similarity matrix
        sim_matrix = embeddings @ embeddings.T  # cosine sim (unit vectors)

        # Step 3 — find converging pairs
        n = len(outputs)
        adjacency: Dict[int, List[int]] = {i: [] for i in range(n)}

        for i, j in combinations(range(n), 2):
            score_gap = abs(outputs[i].numeric_score - outputs[j].numeric_score)
            sem_sim = float(sim_matrix[i, j])

            if score_gap < self._score_gap_threshold and sem_sim >= self._semantic_threshold:
                adjacency[i].append(j)
                adjacency[j].append(i)
                log.debug(
                    "convergence_detector.pair_converging",
                    agent_a=outputs[i].agent_type.value,
                    agent_b=outputs[j].agent_type.value,
                    score_gap=round(score_gap, 4),
                    sem_sim=round(sem_sim, 4),
                )

        # Step 4 — extract connected components (clusters)
        clusters = self._connected_components(adjacency, n)

        # Step 5 — build ConvergenceSignal per cluster
        signals: List[ConvergenceSignal] = []
        for cluster_indices in clusters:
            if len(cluster_indices) < _MIN_GROUP_SIZE:
                continue

            cluster_outputs = [outputs[i] for i in cluster_indices]
            cluster_scores = [o.numeric_score for o in cluster_outputs]
            avg_score = float(np.mean(cluster_scores))
            std_dev = float(np.std(cluster_scores, ddof=0))
            topic = self._infer_topic(cluster_outputs)
            agent_types = [o.agent_type.value for o in cluster_outputs]

            signal = ConvergenceSignal(
                topic=topic,
                converging_agents=agent_types,
                avg_score=round(avg_score, 4),
                score_std_dev=round(std_dev, 4),
                round_number=round_number,
            )
            signals.append(signal)

            log.info(
                "convergence_detector.signal",
                topic=topic,
                agents=agent_types,
                avg_score=avg_score,
                score_std_dev=std_dev,
            )

        log.info(
            "convergence_detector.complete",
            n_signals=len(signals),
        )
        return signals

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Return L2-normalised embeddings for *texts*."""
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
                return embeddings  # type: ignore[return-value]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "convergence_detector.embed_error",
                    error=str(exc),
                    fallback="keyword_overlap",
                )

        # Fallback — keyword-overlap similarity
        return self._keyword_overlap_embeddings(texts)

    def _try_load_embedder(self) -> bool:
        """Lazy-load SentenceTransformer. Returns True on success."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embedder = SentenceTransformer(self._embedding_model_name)
            logger.info(
                "convergence_detector.embedder_loaded",
                model=self._embedding_model_name,
            )
            return True
        except ImportError:
            logger.warning(
                "convergence_detector.sentence_transformers_unavailable",
                fallback="keyword_overlap",
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "convergence_detector.embedder_load_error",
                error=str(exc),
                fallback="keyword_overlap",
            )
            return False

    def _keyword_overlap_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Fallback: represent each text as a bag-of-words TF vector,
        L2-normalised, so that dot products approximate cosine similarity.
        """
        # Build vocabulary
        tokenised = [set(t.lower().split()) for t in texts]
        vocab = sorted({w for tokens in tokenised for w in tokens})
        word_to_idx = {w: i for i, w in enumerate(vocab)}

        dim = max(len(vocab), 1)
        vectors = np.zeros((len(texts), dim), dtype=float)
        for row, tokens in enumerate(tokenised):
            for token in tokens:
                idx = word_to_idx.get(token)
                if idx is not None:
                    vectors[row, idx] += 1.0

        # L2-normalise
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return vectors / norms

    # ------------------------------------------------------------------
    # Graph helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _connected_components(
        adjacency: Dict[int, List[int]],
        n: int,
    ) -> List[List[int]]:
        """BFS/DFS to find all connected components in the adjacency graph."""
        visited = [False] * n
        components: List[List[int]] = []

        for start in range(n):
            if visited[start] or not adjacency[start]:
                continue
            component: List[int] = []
            queue: deque[int] = deque([start])
            while queue:
                node = queue.popleft()
                if visited[node]:
                    continue
                visited[node] = True
                component.append(node)
                for neighbour in adjacency[node]:
                    if not visited[neighbour]:
                        queue.append(neighbour)
            if len(component) >= _MIN_GROUP_SIZE:
                components.append(component)

        return components

    # ------------------------------------------------------------------
    # Topic inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_topic(outputs: List[AnalystOutput]) -> str:
        """
        Derive a short topic label from the converging agents' key_arguments
        by extracting the most common meaningful tokens.
        """
        # Collect all words, filter stopwords, pick top tokens
        stopwords = {
            "the", "a", "an", "and", "or", "but", "is", "are", "was",
            "were", "to", "of", "in", "on", "for", "with", "this", "that",
            "it", "its", "by", "at", "from", "as", "has", "have", "be",
            "not", "will", "their", "they", "we", "our", "which", "while",
        }
        freq: Dict[str, int] = {}
        for o in outputs:
            for word in o.key_argument.lower().split():
                token = word.strip(".,;:!?\"'()-")
                if len(token) > 3 and token not in stopwords:
                    freq[token] = freq.get(token, 0) + 1

        if not freq:
            agent_list = ", ".join(o.agent_type.value for o in outputs)
            return f"convergence: {agent_list}"

        # Top 3 most frequent meaningful terms
        top_terms = sorted(freq, key=freq.__getitem__, reverse=True)[:3]
        return " / ".join(top_terms)
