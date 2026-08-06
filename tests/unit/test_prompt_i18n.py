from eglk_harness.domain.prompt_i18n import constraint_block, prompt_language


def test_en_contains_no_tools():
    assert prompt_language({"EGLK_PROMPT_LANGUAGE": "en"}) == "en"
    block = constraint_block({"EGLK_PROMPT_LANGUAGE": "en"})
    assert "No tools" in block


def test_zh_contains_wu_gongju():
    assert prompt_language({"EGLK_PROMPT_LANGUAGE": "zh"}) == "zh"
    block = constraint_block({"EGLK_PROMPT_LANGUAGE": "zh"})
    assert "无工具" in block
