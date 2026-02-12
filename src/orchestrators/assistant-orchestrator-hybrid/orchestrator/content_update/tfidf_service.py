"""
TF-IDF service for keyword extraction
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from typing import List, Set, Dict, Optional
from sqlalchemy.orm import Session
import logging

from integration.models import AgentRegistry

logger = logging.getLogger(__name__)

class TfidfLearningService:
    def __init__(self):
        pass  # No internal state needed for now

    def get_agent_details(self, session: Session, agent_name: str) -> Optional[Dict]:
        """
        Fetch agent metadata from PostgreSQL database.
        
        Args:
            session: SQLAlchemy session
            agent_name: Name of the agent to fetch
            
        Returns:
            Dictionary with agent details or None if not found
        """
        agent = session.query(AgentRegistry).filter_by(
            agent_name=agent_name,
            is_active=True
        ).first()

        if not agent:
            logger.warning(f"No agent found with name {agent_name}")
            return None

        # Convert description_keywords array to comma-separated string for compatibility
        keywords_str = ",".join(agent.description_keywords) if agent.description_keywords else ""
        
        return {
            "agent_name": agent_name,
            "description": agent.description or "",
            "keywords": keywords_str
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