from content_update.celery_app import celery_app
from content_update.postgres_client import get_session_context
from content_update.tfidf_service import TfidfLearningService

# Import AgentRegistry model from integration package
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from integration.models import AgentRegistry

import logging
logger = logging.getLogger(__name__)

tfidf_service = TfidfLearningService()

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
        with get_session_context() as session:
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
    
    

