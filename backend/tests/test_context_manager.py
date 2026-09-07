from backend.config.schema import ContextConfig
from backend.context.context_manager import ContextManager

CFG = ContextConfig(max_history_pairs=2, resume_path=None, job_description="")


def test_includes_resume_jd_and_question():
    cm = ContextManager(CFG, answer_style="concise")
    cm.set_resume("Built APIs in Python")
    cm.set_job_description("Backend engineer")
    msgs = cm.build_messages("What is your stack?")
    assert msgs[0]["role"] == "user"
    body = msgs[0]["content"]
    assert "Built APIs in Python" in body
    assert "Backend engineer" in body
    assert "What is your stack?" in body
    assert "first person" in cm.system_prompt.lower() or "speaking" in cm.system_prompt.lower()


def test_history_truncated():
    cm = ContextManager(CFG, answer_style="concise")
    cm.add_qa_pair("Q1", "A1")
    cm.add_qa_pair("Q2", "A2")
    cm.add_qa_pair("Q3", "A3")
    body = cm.build_messages("Q4")[0]["content"]
    assert "Q1" not in body
    assert "Q2" in body and "Q3" in body


def test_star_style_mentions_result():
    cm = ContextManager(CFG, answer_style="star_format")
    assert "situation" in cm.system_prompt.lower() or "result" in cm.system_prompt.lower()
