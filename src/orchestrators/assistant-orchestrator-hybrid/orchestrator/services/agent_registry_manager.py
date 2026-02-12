import logging
from typing import Optional, TYPE_CHECKING

from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy.orm import Session

from .database import get_db_session
from .orm_models import AgentRegistry

if TYPE_CHECKING:
    from integration.openai_client import AzureOpenAIClient

logger = logging.getLogger(__name__)


class AgentRegistryManager:
    """Manager class for AgentRegistry CRUD operations."""

    def __init__(
        self,
        openai_client: "AzureOpenAIClient",
        db_session: Session | None = None,
        default_deployment_name: str = "Talk",
    ):
        self._db_session = db_session
        self.openai_client = openai_client
        self.default_deployment_name = default_deployment_name

    @property
    def db(self) -> Session:
        """Get or create a database session."""
        if self._db_session is None:
            self._db_session = get_db_session()
        return self._db_session

    def close(self) -> None:
        """Close the database session if it exists."""
        if self._db_session is not None:
            self._db_session.close()
            self._db_session = None

    @staticmethod
    def extract_keywords_tfidf(text: str, top_n: int = 10) -> list[str]:
        """Extract keywords from text using TF-IDF."""
        vectorizer = TfidfVectorizer(stop_words="english", max_features=top_n)
        try:
            vectorizer.fit_transform([text])
            keywords = vectorizer.get_feature_names_out().tolist()
            return keywords
        except Exception:
            return []

    async def generate_embeddings(self, text: str) -> list[float]:
        """
        Generate embeddings for the given text using Azure OpenAI.
        
        Args:
            text: Text to generate embeddings for
            
        Returns:
            List of embedding floats
        """
        return self.openai_client.generate_embeddings(text)

    def get_agent(self, agent_name: str) -> Optional[AgentRegistry]:
        """Get an agent by name."""
        agent = self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_name == agent_name
        ).first()
        return agent

    def get_all_agents(self) -> list[AgentRegistry]:
        """Get all agents from the registry."""
        agents = self.db.query(AgentRegistry).all()
        return agents

    def get_all_agent_names(self) -> list[str]:
        """Get all agent names from the registry."""
        agents = self.db.query(AgentRegistry.agent_name).all()
        return [agent.agent_name for agent in agents]

    def agent_exists(self, agent_name: str) -> bool:
        """Check if an agent exists."""
        exists = self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_name == agent_name
        ).first() is not None
        return exists

    async def create_agent(
        self,
        agent_name: str,
        description: str,
        desc_keywords: Optional[list[str]] = None,
        deployment_name: Optional[str] = None,
    ) -> dict:
        """Create a new agent in the registry."""
        try:
            # Check if agent already exists
            existing = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name == agent_name
            ).first()
            if existing:
                raise ValueError(f"Agent '{agent_name}' already exists")

            # Generate embeddings
            desc_embeddings = await self.generate_embeddings(description)

            # Extract keywords if not provided
            if desc_keywords is None:
                desc_keywords = self.extract_keywords_tfidf(description)

            # Use default deployment name if not provided
            deployment_name = deployment_name or self.default_deployment_name

            new_agent = AgentRegistry(
                agent_name=agent_name,
                description=description,
                description_embeddings=desc_embeddings,
                description_keywords=desc_keywords,
                deployment_name=deployment_name,
            )
            self.db.add(new_agent)
            self.db.commit()
            self.db.refresh(new_agent)

            logger.info(f"Created agent: {agent_name}")
            return {
                "agent_id": new_agent.id,
                "agent_name": agent_name,
                "description": description,
                "desc_keywords": desc_keywords,
                "deployment_name": deployment_name,
            }
        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating agent {agent_name}: {e}")
            raise

    async def update_agent(
        self,
        agent_name: str,
        description: str,
        desc_keywords: Optional[list[str]] = None,
        deployment_name: Optional[str] = None,
    ) -> dict:
        """Update an existing agent in the registry. Also reactivates if inactive."""
        try:
            agent = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name == agent_name
            ).first()
            if not agent:
                raise ValueError(f"Agent '{agent_name}' not found")

            # Generate embeddings
            desc_embeddings = await self.generate_embeddings(description)

            # Extract keywords if not provided
            if desc_keywords is None:
                desc_keywords = self.extract_keywords_tfidf(description)

            # Use default deployment name if not provided
            deployment_name = deployment_name or self.default_deployment_name

            agent.description = description
            agent.description_embeddings = desc_embeddings
            agent.description_keywords = desc_keywords
            agent.deployment_name = deployment_name
            # Reactivate agent if it was inactive
            agent.is_active = True

            self.db.commit()
            self.db.refresh(agent)

            logger.info(f"Updated agent: {agent_name}")
            return {
                "agent_id": agent.id,
                "agent_name": agent_name,
                "description": description,
                "desc_keywords": desc_keywords,
                "deployment_name": deployment_name,
                "is_active": agent.is_active,
            }
        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating agent {agent_name}: {e}")
            raise

    async def register_or_update_agent(
        self,
        agent_name: str,
        description: str,
        desc_keywords: Optional[list[str]] = None,
        deployment_name: Optional[str] = None,
    ) -> dict:
        """
        Register a new agent or update an existing one.
        If agent exists (active or inactive), update it and reactivate.
        If agent doesn't exist, create it.
        """
        existing = self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_name == agent_name
        ).first()
        
        if existing:
            # Agent exists - update and reactivate
            return await self.update_agent(agent_name, description, desc_keywords, deployment_name)
        else:
            # Agent doesn't exist - create new
            return await self.create_agent(agent_name, description, desc_keywords, deployment_name)

    def soft_delete_agent(self, agent_name: str) -> dict:
        """Soft delete an agent by setting is_active=False."""
        try:
            agent = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name == agent_name
            ).first()
            if not agent:
                raise ValueError(f"Agent '{agent_name}' not found")

            agent.is_active = False
            self.db.commit()

            logger.info(f"Soft deleted agent: {agent_name}")
            return {"agent_name": agent_name, "is_active": False}
        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error soft deleting agent {agent_name}: {e}")
            raise

    def activate_agent(self, agent_name: str) -> dict:
        """Activate an agent by setting is_active=True."""
        try:
            agent = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name == agent_name
            ).first()
            if not agent:
                raise ValueError(f"Agent '{agent_name}' not found")

            agent.is_active = True
            self.db.commit()

            logger.info(f"Activated agent: {agent_name}")
            return {"agent_name": agent_name, "is_active": True}
        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error activating agent {agent_name}: {e}")
            raise

    def soft_delete_agents_not_in_list(self, agent_names: list[str]) -> list[str]:
        """
        Soft delete all agents from the registry that are NOT in the provided list.
        Sets is_active=False for agents not in the list.
        Returns list of soft deleted agent names.
        """
        try:
            # Get all active agents not in the provided list
            agents_to_deactivate = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name.notin_(agent_names),
                AgentRegistry.is_active == True  # noqa: E712
            ).all()

            deactivated_names = []
            for agent in agents_to_deactivate:
                deactivated_names.append(agent.agent_name)
                agent.is_active = False

            self.db.commit()

            if deactivated_names:
                logger.info(f"Soft deleted agents not in list: {deactivated_names}")
            return deactivated_names
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error soft deleting agents not in list: {e}")
            raise

    async def sync_agents(
        self,
        agent_names: list[str],
        agent_name: str,
        description: str,
        desc_keywords: list[str] | None = None,
        deployment_name: str | None = None,
    ) -> dict:
        """
        Sync agents with the registry.
        - Soft deletes (is_active=False) agents in DB but not in agent_names list
        - Creates new agent or updates existing one (reactivates if inactive)
        
        Args:
            agent_names: List of agent names that should be active
            agent_name: The agent to create/update (service_name)
            description: Description for the agent
            desc_keywords: Optional keywords, extracted via TF-IDF if not provided
            deployment_name: Optional deployment name, uses default if not provided
        
        Returns summary of operations performed.
        """
        created = []
        updated = []
        deactivated = []
        reactivated = []
        errors = []

        # Soft delete agents not in the provided list
        try:
            deactivated = self.soft_delete_agents_not_in_list(agent_names)
        except Exception as e:
            errors.append({"operation": "sync_deactivate", "error": str(e)})

        # Register or update the agent
        try:
            existing = self.db.query(AgentRegistry).filter(
                AgentRegistry.agent_name == agent_name
            ).first()
            
            if existing:
                was_inactive = not existing.is_active
                await self.register_or_update_agent(agent_name, description, desc_keywords, deployment_name)
                updated.append(agent_name)
                if was_inactive:
                    reactivated.append(agent_name)
                    logger.info(f"Reactivated agent: {agent_name}")
            else:
                await self.register_or_update_agent(agent_name, description, desc_keywords, deployment_name)
                created.append(agent_name)
        except Exception as e:
            errors.append({"agent_name": agent_name, "error": str(e)})

        return {
            "created": created,
            "updated": updated,
            "reactivated": reactivated,
            "deactivated": deactivated,
            "errors": errors,
        }
