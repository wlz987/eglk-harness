import pytest

from eglk_harness.domain.kernel.leaf_contract import assemble_leaf_contract
from eglk_harness.domain.kernel.tree import make_root


def test_assemble_basic() -> None:
    tree = make_root("Implement lexer", ["tokenize keywords"])
    leaf = tree.in_progress()
    assert leaf is not None
    c = assemble_leaf_contract(
        leaf,
        tick=3,
        goal_constraints=["do not edit tests"],
        prior_evidence=[{"kind": "gap", "text": "missed NULL literal", "ref": "t1"}],
    )
    assert c.leaf_id == "root"
    assert c.acceptance == ["tokenize keywords"]
    assert "do not edit tests" in c.boundary
    assert c.tick == 3
    maker = c.render_maker_block()
    assert "missed NULL literal" in maker
    checker = c.render_checker_block()
    assert "LEAF_CONTRACT" in checker


def test_assemble_requires_criteria() -> None:
    tree = make_root("x", ["ok"])
    leaf = tree.root
    leaf.done_criteria = []
    with pytest.raises(ValueError):
        assemble_leaf_contract(leaf)


def test_verifier_challenges_become_prior() -> None:
    tree = make_root("x", ["ok"])
    tree.root.verifier_challenges = ["float noise"]
    c = assemble_leaf_contract(tree.root)
    assert any(
        isinstance(p, dict) and p.get("text") == "float noise" for p in c.prior_evidence
    )
