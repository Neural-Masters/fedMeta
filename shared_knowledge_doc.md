If I want to store learned knowledge for Tool calling or user's other thing that can be shared to other user's also How I can do?

ANSWER---------------------------------------------------------------

Use Learned Knowledge with a shared Knowledge instance and the "global" namespace. In Agentic mode, Agno gives the agent save_learning and search_learnings tools, so it can save reusable insights and retrieve them for any user who uses that same store. 1
python

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.knowledge import Knowledge
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.learn import LearningMachine, LearningMode, LearnedKnowledgeConfig
from agno.models.openai import OpenAIResponses
from agno.vectordb.pgvector import PgVector, SearchType

db = PostgresDb(
    db_url="postgresql+psycopg://ai:ai@localhost:5532/ai"
)

# This vector-backed Knowledge instance is shared by all agents/users.
shared_learnings = Knowledge(
    vector_db=PgVector(
        db_url="postgresql+psycopg://ai:ai@localhost:5532/ai",
        table_name="shared_learnings",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    ),
)

agent = Agent(
    model=OpenAIResponses(id="gpt-5.2"),
    db=db,
    learning=LearningMachine(
        knowledge=shared_learnings,
        learned_knowledge=LearnedKnowledgeConfig(
            mode=LearningMode.AGENTIC,
            namespace="global",
        ),
    ),
)

Then a user can ask the agent to save a reusable insight:
python

agent.print_response(
    "Save this: Check cloud egress costs before comparing providers.",
    user_id="alice@example.com",
)

A different user of the same agent/store can benefit from it later:
python

agent.print_response(
    "What should I compare between cloud providers?",
    user_id="bob@example.com",
)

For direct application-side retrieval, query the learning store with the same global namespace:
python

results = agent.learning_machine.learned_knowledge_store.search(
    query="cloud provider costs",
    namespace="global",
    limit=5,
)

Use "global" for knowledge shared by everyone, or set a custom namespace such as "engineering" to share only within that group.