from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.format_scratchpad.tools import format_to_tool_messages
from langchain.agents.output_parsers.tools import ToolsAgentOutputParser
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI

from ai_search.agents.prompts import ANALYST_PROMPT, PLAN_PROMPT
from ai_search.config.settings import settings


def build_agent(tools: Sequence):
    """Create the planner chain and Gemini tools agent."""
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    llm_kwargs = {
        "model": settings.model_name,
        "temperature": 0,
        "api_key": settings.google_api_key,
        "convert_system_message_to_human": True,
    }
    planner_llm = ChatGoogleGenerativeAI(**llm_kwargs)
    agent_llm = ChatGoogleGenerativeAI(**llm_kwargs)

    planner_prompt = ChatPromptTemplate.from_messages([
        ("system", PLAN_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
    ])

    select_planner_inputs = RunnableLambda(
        lambda x: {
            "input": x["input"],
            "chat_history": x.get("chat_history", []),
        }
    )

    planner_chain = (
        select_planner_inputs
        | planner_prompt
        | planner_llm
        | StrOutputParser()
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", ANALYST_PROMPT),
        (
            "system",
            "아래의 '분석 계획 초안'을 충실히 반영해 답변해 주세요.\n{analysis_plan}",
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    llm_with_tools = agent_llm.bind_tools(tools)

    agent = (
        {
            "input": lambda x: x["input"],
            "analysis_plan": lambda x: x.get("analysis_plan") or planner_chain.invoke(x),
            "agent_scratchpad": lambda x: format_to_tool_messages(x.get("intermediate_steps", [])),
            "chat_history": lambda x: x.get("chat_history", []),
        }
        | prompt
        | llm_with_tools
        | ToolsAgentOutputParser()
    )

    return planner_chain, agent
