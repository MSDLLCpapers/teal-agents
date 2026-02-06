from content_update.celery_app import celery_app
from content_update.chroma_client import get_collection
from content_update.tfidf_service import TfidfLearningService


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
    logger.info("Started metadata update for %s", agent_name)
    logger.info("kw list %s", agent_response)

    collection = get_collection()
    logger.info("....gathering agent details....")
    agent_info = tfidf_service.get_agent_details(collection,agent_name)
    new_keywords ,updated_key_words= tfidf_service.learn_keywords(agent_info, agent_name, agent_response)
    logger.info(".....new learned kewords...."+str(new_keywords))
    try:
        collection.update(
            ids=[agent_name],
            metadatas=[{"desc_keywords": ",".join(updated_key_words)}]
        )
    except Exception:
        logger.exception("Chroma update failed")
        raise

    logger.warning("Metadata update successful for %s", agent_name)
    return True


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
    
    

