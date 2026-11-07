"""U2: rule edges."""
from app import config, rules


def test_size_boundary_between_routine_and_heavy():
    prompt = "Write a commit message"
    assert rules.classify(3_999, False, prompt) == "routine"
    assert rules.classify(4_000, False, prompt) == "heavy"


def test_tools_stop_a_task_counting_as_routine():
    assert rules.classify(100, True, "Write a commit message") == "heavy"


def test_design_work_is_deep():
    assert rules.classify(100, False, "Design a failover architecture") == "deep"


def test_runs_above_compares_cost_and_ignores_unknown_models():
    assert rules.runs_above(config.OPUS, config.HAIKU)
    assert rules.runs_above(config.SONNET, config.HAIKU)
    assert not rules.runs_above(config.HAIKU, config.OPUS)
    assert not rules.runs_above(config.OPUS, config.OPUS)
    assert not rules.runs_above("some-other-model", config.HAIKU)


def test_keyword_matches_whole_words_only():
    assert rules.classify(100, False, "Explain information theory") == "grey"


def test_reminders_and_tool_results_are_not_human_text():
    messages = [{
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ignored"},
            {"type": "text", "text": "<system-reminder>\nignored\n</system-reminder>"},
        ],
    }]
    assert rules.last_user_text(messages) == ""


def test_keep_tag_needs_to_stand_alone():
    assert rules.has_keep_tag("Commit and push #keep")
    assert rules.has_keep_tag("#KEEP commit and push")
    assert not rules.has_keep_tag("See issue#keep")
    assert not rules.has_keep_tag("Commit and push")


def test_routine_only_covers_prompts_that_lead_with_it():
    assert rules.classify(30, False, "Commit and push") == "routine"
    assert rules.classify(30, False, "Please git push origin main") == "routine"
    assert rules.classify(30, False, "Look up the Python version") == "routine"
    assert rules.classify(30, False, "Refactor auth, then commit and push") == "grey"


def test_commit_message_wording_does_not_count_as_investigation():
    text = "Write a commit message for: fix failing bug in login"
    assert rules.classify(30, False, text) == "routine"


def test_investigation_outranks_routine():
    assert rules.classify(30, False, "Push failed, figure out why") == "deep"
    assert rules.classify(30, False, "What is wrong with this query?") == "deep"


def test_long_lookups_are_not_routine():
    question = "Which of these two config files does the server load?"
    assert rules.classify(30, False, question) == "routine"
    assert rules.classify(config.ROUTINE_MAX_TOKENS, False, question) == "grey"


def test_routine_stays_on_haiku_and_deep_stays_above_it_at_every_level():
    for info in config.LEVELS.values():
        assert info["routes"]["routine"] == config.HAIKU
        assert info["routes"]["deep"] != config.HAIKU


def _failures(count, error="boom"):
    messages = [{"role": "user", "content": "go"}]
    for i in range(count):
        messages.append({
            "role": "assistant",
            "content": [{"type": "tool_use", "id": f"t{i}", "name": "run_sql", "input": {}}],
        })
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result", "tool_use_id": f"t{i}", "is_error": True, "content": error,
            }],
        })
    return messages


def test_loop_boundary():
    assert rules.is_loop(_failures(2))[0] is False
    assert rules.is_loop(_failures(3)) == (True, 3, "run_sql")


def test_different_errors_are_not_a_loop():
    messages = _failures(2, "first") + _failures(2, "second")[1:]
    assert rules.is_loop(messages)[0] is False


def test_success_or_human_message_clears_the_count():
    success = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t9", "content": "rows: 5"}],
    }
    assert rules.repeated_tool_errors(_failures(3) + [success])[0] == 0
    human = {"role": "user", "content": "try another way"}
    assert rules.repeated_tool_errors(_failures(3) + [human])[0] == 0
