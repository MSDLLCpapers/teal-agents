from content_update.celery_app import celery_app
from content_update.chroma_client import get_collection

import logging
logger = logging.getLogger(__name__)

@celery_app.task
def dummy_task(a, b):
    #count = my_collection.count()
    #logger.info("Chroma collection count: %s", count)
    print(f"Running dummy task: {a} + {b}")
    return a + b


@celery_app.task(bind=True)
def update_metadata(self, agent_name, key_word_list):
    logger.info("Started metadata update for %s", agent_name)
    logger.info("kw list %s", key_word_list)

    collection = get_collection()

    try:
        collection.update(
            ids=[agent_name],
            metadatas=[{"desc_keywords": key_word_list}]
        )
    except Exception:
        logger.exception("Chroma update failed")
        raise

    logger.warning("Metadata update successful for %s", agent_name)
    return True
    
    

