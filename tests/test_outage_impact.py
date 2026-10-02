import unittest

from aquaflow.outage.impact import Customer, summarize
from aquaflow.workflow_service import WorkflowService


class OutageImpactTest(unittest.TestCase):
    def test_one_account_multiple_people_counts_residents_not_accounts(self):
        # Two accounts: a high-density building (120 residents) and a house (3).
        rows = [
            Customer("tower", "N1", False, 120),
            Customer("house", "N2", False, 3),
        ]
        result = summarize(rows, {"N1", "N2"})
        self.assertEqual(result["accounts"], 2)
        self.assertEqual(result["population"], 123)
        self.assertEqual(result["critical"], 0)

    def test_tiny_population_critical_user_counted_independently(self):
        # Care facility: only a handful of residents but a critical account.
        rows = [Customer("clinic", "N1", True, 4)]
        result = summarize(rows, {"N1"})
        self.assertEqual(result["accounts"], 1)
        self.assertEqual(result["population"], 4)
        self.assertEqual(result["critical"], 1)

    def test_critical_user_without_residents_still_notifies(self):
        # A critical account with zero residents must still drive notification;
        # the critical count is independent of the population calculation.
        out = WorkflowService().run(
            "outage_impact",
            {"customers": [{"account": "pump-station", "node": "N1", "critical": True, "population": 0}], "nodes": ["N1"]},
        )
        self.assertEqual(out["decision"], "notify")
        self.assertEqual(out["value"]["accounts"], 1)
        self.assertEqual(out["value"]["population"], 0)
        self.assertEqual(out["value"]["critical"], 1)

    def test_high_density_aggregation_through_workflow(self):
        out = WorkflowService().run(
            "outage_impact",
            {
                "customers": [
                    {"account": "tower", "node": "N1", "critical": False, "population": 120},
                    {"account": "clinic", "node": "N2", "critical": True, "population": 6},
                ],
                "nodes": ["N1", "N2"],
            },
        )
        self.assertEqual(out["decision"], "notify")
        self.assertEqual(out["value"]["accounts"], 2)
        self.assertEqual(out["value"]["population"], 126)
        self.assertEqual(out["value"]["critical"], 1)
        self.assertEqual(out["audit"]["contract"], "v1")

    def test_customers_outside_outage_nodes_are_excluded(self):
        rows = [
            Customer("tower", "N1", False, 120),
            Customer("clinic", "N9", True, 6),
            Customer("house", "N9", False, 4),
        ]
        # Only N1 is in the isolated/outage node set; N9 customers keep supply.
        result = summarize(rows, {"N1"})
        self.assertEqual(result, {"accounts": 1, "population": 120, "critical": 0})

    def test_no_affected_customers_clears(self):
        out = WorkflowService().run(
            "outage_impact",
            {
                "customers": [
                    {"account": "house", "node": "N9", "critical": False, "population": 4},
                    {"account": "clinic", "node": "N9", "critical": True, "population": 6},
                ],
                "nodes": ["N1"],
            },
        )
        self.assertEqual(out["decision"], "clear")
        self.assertEqual(out["value"], {"accounts": 0, "population": 0, "critical": 0})


if __name__ == "__main__":
    unittest.main()
