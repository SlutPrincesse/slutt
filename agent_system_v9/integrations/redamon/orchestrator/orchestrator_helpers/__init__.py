"""Orchestrator helper functions.

This module contains helper functions extracted from the main orchestrator
to keep the architectural flow clear and maintainable.
"""

from .chain_graph_writer import (
    close_driver as close_chain_graph_driver,
)

# config MUST be imported before phase/chain_graph_writer
# to avoid circular import: phase -> prompts -> utils -> orchestrator_helpers.get_checkpointer
from .config import (
    create_config,
    get_checkpointer,
    get_config_values,
    get_identifiers,
    get_thread_id,
    is_session_config_complete,
    set_checkpointer,
)
from .debug import (
    save_graph_image,
)
from .json_utils import (
    DateTimeEncoder,
    extract_json,
    json_dumps_safe,
    normalize_content,
)
from .llm_setup import (
    apply_project_settings,
    parse_model_provider,
    setup_llm,
)
from .nodes import (
    await_approval_node,
    await_question_node,
    execute_tool_node,
    generate_response_node,
    initialize_node,
    process_answer_node,
    process_approval_node,
    think_node,
)
from .parsing import (
    parse_analysis_response,
    parse_llm_decision,
    try_parse_llm_decision,
)
from .phase import (
    classify_attack_path,
    determine_phase_for_new_objective,
)
from .streaming import (
    detect_generated_file,
    emit_streaming_events,
)

__all__ = [
    # json_utils
    "DateTimeEncoder",
    "json_dumps_safe",
    "normalize_content",
    "extract_json",
    # parsing
    "parse_llm_decision",
    "try_parse_llm_decision",
    "parse_analysis_response",
    # config
    "set_checkpointer",
    "get_checkpointer",
    "get_thread_id",
    "create_config",
    "get_config_values",
    "get_identifiers",
    "is_session_config_complete",
    # phase
    "classify_attack_path",
    "determine_phase_for_new_objective",
    # chain_graph_writer
    "close_chain_graph_driver",
    # debug
    "save_graph_image",
    # llm_setup
    "parse_model_provider",
    "setup_llm",
    "apply_project_settings",
    # streaming
    "detect_generated_file",
    "emit_streaming_events",
    # nodes
    "initialize_node",
    "think_node",
    "execute_tool_node",
    "generate_response_node",
    "await_approval_node",
    "process_approval_node",
    "await_question_node",
    "process_answer_node",
]
