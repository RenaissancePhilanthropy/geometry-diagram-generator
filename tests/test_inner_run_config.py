"""An inner strategy run must not inherit the caller's LangGraph `configurable`
(thread_id, checkpoint ids, ...): those address the caller's graph, and the inner
graphs have no checkpointer of their own. Everything else (callbacks, tags,
metadata, run_name) still flows through."""
from geometry_diagrams.strategies.llm import config_kwargs
from geometry_diagrams.strategies.recipe import RecipeStrategy

CALLER = {
    "configurable": {"thread_id": "t1", "checkpoint_ns": "outer", "__pregel_checkpointer": object()},
    "tags": ["geo"],
    "metadata": {"user": "u"},
    "run_name": "outer",
}


def test_run_config_drops_configurable_but_keeps_the_rest():
    built = RecipeStrategy()._build_run_config(CALLER)
    assert "configurable" not in built
    assert built["tags"] == ["geo"] and built["metadata"] == {"user": "u"} and built["run_name"] == "outer"


def test_caller_config_is_not_mutated():
    snapshot = dict(CALLER)
    RecipeStrategy()._build_run_config(CALLER)
    assert CALLER == snapshot


def test_direct_llm_call_config_drops_configurable():
    passed = config_kwargs(CALLER)["config"]
    assert "configurable" not in passed and passed["tags"] == ["geo"]


def test_config_with_only_configurable_passes_nothing():
    assert config_kwargs({"configurable": {"thread_id": "t1"}}) == {}
