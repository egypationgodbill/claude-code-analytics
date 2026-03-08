from suggestions import generate_suggestions


def test_empty_metrics_returns_info():
    result = generate_suggestions({"empty": True}, {}, {}, {}, {})
    assert len(result) == 1
    assert result[0]["type"] == "info"


def test_short_prompts_many_messages_suggests_context():
    prompt = {
        "avg_words": 10,
        "specificity_rate": 50,
        "question_ratio": 20,
        "file_ref_rate": 10,
        "code_block_rate": 5,
        "timeline": [],
    }
    efficiency = {"avg_messages_per_session": 15, "sessions": []}
    result = generate_suggestions(prompt, {"plan_mode_count": 0, "subagent_types": {}}, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Add More Upfront Context" in titles


def test_short_prompts_few_messages_positive():
    prompt = {
        "avg_words": 10,
        "specificity_rate": 50,
        "question_ratio": 20,
        "file_ref_rate": 10,
        "code_block_rate": 5,
        "timeline": [],
    }
    efficiency = {"avg_messages_per_session": 3, "sessions": []}
    result = generate_suggestions(prompt, {"plan_mode_count": 0, "subagent_types": {}}, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Efficient Short Prompts" in titles


def test_no_signals_returns_looking_good():
    prompt = {
        "avg_words": 25,
        "specificity_rate": 50,
        "question_ratio": 30,
        "file_ref_rate": 10,
        "code_block_rate": 5,
        "timeline": [],
    }
    efficiency = {"avg_messages_per_session": 5, "sessions": []}
    tools = {"plan_mode_count": 1, "subagent_types": {}}
    result = generate_suggestions(prompt, tools, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Looking Good" in titles


def test_high_context_window_warning():
    prompt = {
        "avg_words": 25,
        "specificity_rate": 50,
        "question_ratio": 30,
        "file_ref_rate": 10,
        "code_block_rate": 5,
        "timeline": [],
    }
    efficiency = {"avg_messages_per_session": 5, "sessions": []}
    tools = {"plan_mode_count": 1, "subagent_types": {}}
    model = {
        "sessions_over_75pct": 3,
        "max_utilization": 95,
        "avg_peak_utilization": 60,
    }
    result = generate_suggestions(prompt, tools, efficiency, {}, model)
    titles = [s["title"] for s in result]
    assert "High Context Window Usage" in titles
