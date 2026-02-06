"""
TF-IDF service for keyword extraction
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from typing import List, Set,Dict,Optional
import logging

logger = logging.getLogger(__name__)

class TfidfLearningService:
    def __init__(self):
        pass  # No internal state needed for now

    def get_agent_details(self, collection, agent_name: str) -> Optional[Dict]:
        """
        Fetch agent metadata from Chroma collection.
        """
        results = collection.get(
            where={"agent_name": agent_name},
            include=["metadatas"]
        )

        if not results.get("metadatas"):
            logger.warning(f"No metadata found for agent {agent_name}")
            return None

        meta = results["metadatas"][0]
        return {
            "agent_name": agent_name,
            "description": meta.get("description", ""),
            "keywords": meta.get("desc_keywords", "")
        }

    def extract_tfidf_keywords(self, answer: str, corpus: List[str], top_k: int = 5) -> Set[str]:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1
        )
        vectorizer.fit(corpus)
        vec = vectorizer.transform([answer])
        scores = vec.toarray()[0]
        features = vectorizer.get_feature_names_out()
        top_idx = scores.argsort()[-top_k:]
        return {features[i].lower() for i in top_idx if scores[i] > 0}

    def learn_keywords(self, agent_registry: dict, agent_name: str, answer: str) -> List[str]:
        corpus = [f"{agent_registry.get('description','')} {agent_registry.get('keywords','')}"]
        learned = self.extract_tfidf_keywords(answer, corpus)
        existing = {k.strip().lower() for k in agent_registry.get("keywords", "").split(",") if k.strip()}
        additions = learned - existing
        added_latest = additions | existing
        #agent_registry["desc_keywords_candidate"] = ",".join(sorted(existing | additions))
        logger.info(f"TFIDF | agent={agent_name} | new_keywords={additions}")
        logger.info(f"TFIDF | agent={agent_name} | existing_keywords={existing}")
        logger.info(f"TFIDF | agent={agent_name} | existing_keywords={added_latest}")
        return additions,added_latest