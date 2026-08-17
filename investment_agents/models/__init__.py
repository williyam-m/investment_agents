"""
Data models package.

Public surface
--------------
* AgentType, AnalystOutput, Recommendation  — agent-level output models
* DebateRequest, DebateTrace                — debate lifecycle models
* CommitteeMemo                             — final synthesis output
"""
from investment_agents.models.agent_output import (
    AgentType,
    AnalystOutput,
    Recommendation,
)
from investment_agents.models.debate import DebateRequest, DebateTrace
from investment_agents.models.synthesis import CommitteeMemo

__all__ = [
    "AgentType",
    "AnalystOutput",
    "Recommendation",
    "DebateRequest",
    "DebateTrace",
    "CommitteeMemo",
]
