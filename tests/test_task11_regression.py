"""Task 11 regression patterns (WA-Hard eglk) — mechanical Gate expectations."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.repair_counts import closure_repair_key


class Task11RegressionFixture(unittest.TestCase):
  """Frozen scenarios distilled from WA-Hard task 11 audit (empty claim / closure repairs)."""

  def test_empty_actions_claim_missing_alternatives_repair(self) -> None:
    contract = {
      "contract_id": "wc-t11",
      "node_id": "leaf",
      "obligation_refs": ["ob-1"],
      "transaction_policy": {"side_effect_class_ceiling": ["read_only", "reversible"]},
    }
    claim = {
      "actions": [],
      "alternatives": [],
      "contract_ref": "wc-t11",
    }
    evidence = {
      "world_revision": 0,
      "verdicts": [
        {
          "obligation_id": "ob-1",
          "status": "unsatisfied",
          "attestations": [],
          "gaps": ["no_attestation"],
        }
      ],
      "integrity_violation": False,
      "additional_gaps": [],
    }
    d = decide(contract, claim, evidence, quota={"cognitive_tokens": 0, "repairs_max": 8})
    self.assertEqual(d.decision, "repair")
    self.assertEqual(d.reason, "missing_alternatives")

  def test_closure_incomplete_counts_toward_repairs_max(self) -> None:
    key = closure_repair_key()
    counts = {key: 8}
    contract = {
      "contract_id": "wc-root",
      "node_id": "root",
      "obligation_refs": ["ob-root"],
      "transaction_policy": {"side_effect_class_ceiling": ["read_only"]},
    }
    claim = {
      "actions": [],
      "alternatives": [{"text": "none", "status": "reject"}],
      "contract_ref": "wc-root",
    }
    evidence = {
      "world_revision": 1,
      "verdicts": [],
      "integrity_violation": False,
      "additional_gaps": [],
    }
    d = decide(
      contract,
      claim,
      evidence,
      quota={"cognitive_tokens": 0, "repairs_max": 8},
      repair_counts=counts,
      is_closure_gate=True,
      closure_complete=False,
    )
    self.assertEqual(d.decision, "abort")
    self.assertEqual(d.reason, "closure_incomplete_exhausted")


if __name__ == "__main__":
  unittest.main()
