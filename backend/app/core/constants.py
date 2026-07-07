"""Project-wide constants and enumerations.

No magic numbers/strings elsewhere in the codebase -- declare them here.
"""

from __future__ import annotations

from enum import StrEnum

API_V1_PREFIX = "/api/v1"

# --- Agent roles ---


class AgentRole(StrEnum):
    """Layers of the agent hierarchy."""

    ORCHESTRATOR = "orchestrator"
    MAIN = "main"
    SUBAGENT = "subagent"
    REVIEWER = "reviewer"


# Hard cap on subtasks a Main Agent may plan, regardless of max_iterations.
MAX_SUBTASKS = 6

# Per-step response budgets for structured agent calls. Generous because
# reasoning models (e.g. Qwen3) spend output tokens on <think> blocks before
# the JSON. Subagent deliverables stay unbounded (no constant).
ROUTE_MAX_TOKENS = 512
PLAN_MAX_TOKENS = 1536
REVIEW_MAX_TOKENS = 768
SYNTHESIS_MAX_TOKENS = 4096


# --- Task lifecycle ---


class TaskStatus(StrEnum):
    """Lifecycle states of a task session."""

    PENDING = "pending"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class SubagentStatus(StrEnum):
    """Status field of the structured subagent output (see CLAUDE.md 5.4)."""

    SUCCESS = "success"
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"


# --- LLM providers (BYOK + free tier) ---


class LLMProvider(StrEnum):
    """Supported LLM/API-key providers."""

    OLLAMA = "ollama"  # free/local tier (default)
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"  # free tier via Google AI Studio key (BYOK)
    X = "x"
    GITHUB = "github"
    CUSTOM = "custom"


# Providers that actually drive LLM generation (subset of LLMProvider).
LLM_CHAT_PROVIDERS = frozenset(
    {LLMProvider.OLLAMA, LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.GEMINI}
)


# --- WebSocket event types (task/architect live stream) ---


class EventType(StrEnum):
    """Server -> client WebSocket event kinds."""

    TASK_STARTED = "task_started"
    NODE_UPDATE = "node_update"  # an agent node changed state
    AGENT_MESSAGE = "agent_message"  # message passed between agents
    REVIEW_RESULT = "review_result"
    AGENT_QUESTION = "agent_question"  # human-in-the-loop: agent asks the user
    USER_ANSWER = "user_answer"  # human-in-the-loop: user's reply
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    ERROR = "error"


# --- MongoDB collection names ---


class MongoCollection(StrEnum):
    AGENT_LOGS = "agent_logs"
    TASK_SESSIONS = "task_sessions"
    MARKETPLACE_ITEMS = "marketplace_items"
    AGENT_CONFIGURATIONS = "agent_configurations"
    DOCUMENTS = "documents"


# --- Qdrant collection names ---
QDRANT_CONVERSATION_MEMORIES = "conversation_memories"
QDRANT_DOCUMENT_CHUNKS = "document_chunks"

# --- Document ingestion (RAG) ---
# Character-based chunking (approximate; keeps ingestion dependency-free).
DOCUMENT_CHUNK_SIZE = 1000
DOCUMENT_CHUNK_OVERLAP = 150
# Accepted upload types for the current tier (plain text / markdown only).
DOCUMENT_ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".markdown"})
DOCUMENT_MAX_BYTES = 2_000_000  # 2 MB upload cap


# --- Google Gemini (OpenAI-compatible endpoint) ---
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


# --- Anthropic (Claude) Messages API ---
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Anthropic requires an explicit max_tokens on every request.
ANTHROPIC_DEFAULT_MAX_TOKENS = 2048


# --- Billing: rough cost estimate per 1K tokens (USD), by provider ---
# Free/local tiers cost nothing; BYOK providers use conservative blended rates.
PROVIDER_COST_PER_1K_TOKENS: dict[str, float] = {
    LLMProvider.OLLAMA.value: 0.0,
    LLMProvider.OPENAI.value: 0.0015,
    LLMProvider.ANTHROPIC.value: 0.006,
    LLMProvider.GEMINI.value: 0.0,  # free tier (Google AI Studio)
}


# --- Web search tool (subagent JSON directive protocol) ---
WEB_SEARCH_ACTION = "web_search"  # matches the TOOL_CATALOG id
WEB_SEARCH_CATEGORIES = frozenset({"text", "news"})
WEB_SEARCH_DEFAULT_CATEGORY = "text"
WEB_SEARCH_SNIPPET_MAX_CHARS = 500
WEB_SEARCH_RESULTS_OPEN = "<web_search_results>"
WEB_SEARCH_RESULTS_CLOSE = "</web_search_results>"


# --- Agent tool catalog (declarable capabilities for custom agents) ---
# web_search is executed via the subagent directive loop; the rest are
# declared metadata for the current tier, not yet executed.
TOOL_CATALOG: tuple[dict[str, str], ...] = (
    {"id": "web_search", "label": "Web Search"},
    {"id": "code_execution", "label": "Code Execution"},
    {"id": "data_fetch", "label": "Data Fetch (HTTP/API)"},
    {"id": "summarize", "label": "Summarize"},
    {"id": "sentiment_analysis", "label": "Sentiment Analysis"},
    {"id": "file_read", "label": "File / Document Read"},
)

TOOL_IDS = frozenset(tool["id"] for tool in TOOL_CATALOG)
