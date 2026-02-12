from content_update.celery_app import celery_app
from content_update.tfidf_service import TfidfLearningService
from integration.postgres_client import PostgresClient
from integration.models import AgentRegistry
from configs import CONFIGS

from ska_utils import AppConfig

import logging
logger = logging.getLogger(__name__)

# Module-level instances for Celery worker process
# Each forked worker will have its own instance
_postgres_client = None
tfidf_service = TfidfLearningService()


def _get_postgres_client() -> PostgresClient:
    """
    Get or create PostgresClient instance for Celery worker.
    
    This is lazily initialized per worker process. Since Celery workers
    run in separate processes from FastAPI, they need their own DB client.
    We use skip_embeddings=True since workers only need DB access, not vector search.
    """
    global _postgres_client
    if _postgres_client is None:
        # Ensure AppConfig is initialized with all configs in the Celery worker process,
        # since workers run in separate forked processes from FastAPI.
        AppConfig.add_configs(CONFIGS)
        _postgres_client = PostgresClient(skip_embeddings=True)
        logger.info("PostgresClient initialized for Celery worker (embeddings disabled)")
    return _postgres_client

@celery_app.task
def dummy_task(a, b):
    #count = my_collection.count()
    #logger.info("Chroma collection count: %s", count)
    print(f"Running dummy task: {a} + {b}")
    return a + b

@celery_app.task(bind=True)
def update_metadata(self, agent_name, agent_response):
    """
    Update agent metadata with newly learned keywords from TF-IDF analysis.
    
    Args:
        agent_name: Name of the agent to update
        agent_response: The agent's response text to analyze
    """
    logger.info("Started metadata update for %s", agent_name)
    logger.info("Agent response: %s", agent_response)

    try:
        postgres_client = _get_postgres_client()
        
        with postgres_client.get_session_context() as session:
            # Get agent details from database
            logger.info("Gathering agent details from PostgreSQL...")
            agent_info = tfidf_service.get_agent_details(session, agent_name)
            
            if not agent_info:
                logger.warning(f"Agent {agent_name} not found in database, skipping update")
                return False
            
            # Extract new keywords using TF-IDF
            new_keywords, updated_keywords = tfidf_service.learn_keywords(
                agent_info, agent_name, agent_response
            )
            logger.info("New learned keywords: %s", new_keywords)
            
            # Update the agent record in PostgreSQL
            agent = session.query(AgentRegistry).filter_by(agent_name=agent_name).first()
            
            if agent:
                # Convert comma-separated string back to list for database storage
                keywords_list = list(updated_keywords) if updated_keywords else []
                agent.description_keywords = keywords_list
                
                session.commit()
                logger.info("PostgreSQL metadata update successful for %s", agent_name)
                return True
            else:
                logger.warning(f"Agent {agent_name} not found for update")
                return False
                
    except Exception as e:
        logger.exception("PostgreSQL update failed for agent %s: %s", agent_name, str(e))
        raise


# @celery_app.task(bind=True)
# def update_metadata(self, agent_name, key_word_list):
#     logger.info("Started metadata update for %s", agent_name)
#     logger.info("kw list %s", key_word_list)

#     collection = get_collection()


#     try:
#         collection.update(
#             ids=[agent_name],
#             metadatas=[{"desc_keywords": key_word_list}]
#         )
#     except Exception:
#         logger.exception("Chroma update failed")
#         raise

#     logger.warning("Metadata update successful for %s", agent_name)
#     return True
    
    

