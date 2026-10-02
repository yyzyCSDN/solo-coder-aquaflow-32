import unittest

from aquaflow.outage.impact import Customer, summarize
from aquaflow.workflow_rules import evaluate
from aquaflow.workflow_service import WorkflowService


def payload(customers, nodes):
    return {"customers": customers, "nodes": sorted(nodes)}


CUSTOMERS = [
    # 高密度住宅：一个账户对应多人
    {"account": "BLDG-HIGHRISE", "node": "A", "critical": False, "population": 120},
    # 照护设施：居民很少，但属于关键用户
    {"account": "CARE-HOME", "node": "A", "critical": True, "population": 3},
    # 普通住户：一人一账户
    {"account": "RES-1", "node": "A", "critical": False, "population": 1},
    # 不在停水节点集合中：人口密集且关键，但不能计入
    {"account": "HOSPITAL-OTHER", "node": "B", "critical": True, "population": 400},
    {"account": "BLDG-OTHER", "node": "B", "critical": False, "population": 300},
]


class TestSummarize(unittest.TestCase):
    def test_one_account_covers_many_people(self):
        rows = [Customer("BLDG-HIGHRISE", "A", False, 120)]
        result = summarize(rows, {"A"})
        self.assertEqual(result["accounts"], 1)
        self.assertEqual(result["population"], 120)
        self.assertEqual(result["critical"], 0)

    def test_small_population_critical_user_counted_independently(self):
        rows = [Customer("CARE-HOME", "A", True, 3)]
        result = summarize(rows, {"A"})
        self.assertEqual(result["accounts"], 1)
        self.assertEqual(result["population"], 3)
        # 关键用户必须独立统计，不能被人口计算替代
        self.assertEqual(result["critical"], 1)

    def test_zero_population_critical_user_still_counted(self):
        rows = [Customer("PUMP-STATION", "A", True, 0)]
        result = summarize(rows, {"A"})
        self.assertEqual(result["population"], 0)
        self.assertEqual(result["critical"], 1)

    def test_customers_outside_outage_nodes_excluded(self):
        rows = [
            Customer("HOSPITAL-OTHER", "B", True, 400),
            Customer("BLDG-OTHER", "B", False, 300),
        ]
        result = summarize(rows, {"A"})
        self.assertEqual(result, {"accounts": 0, "population": 0, "critical": 0})

    def test_mixed_impact_aggregates_three_metrics_independently(self):
        rows = [Customer(c["account"], c["node"], c["critical"], c["population"]) for c in CUSTOMERS]
        result = summarize(rows, {"A"})
        self.assertEqual(result["accounts"], 3)
        self.assertEqual(result["population"], 124)
        self.assertEqual(result["critical"], 1)


class TestNotificationDecision(unittest.TestCase):
    def run_service(self, customers, nodes):
        return WorkflowService().run("outage_impact", payload(customers, nodes))

    def test_multi_person_account_triggers_notify_via_service(self):
        out = self.run_service([CUSTOMERS[0]], {"A"})
        self.assertEqual(out["decision"], "notify")
        self.assertEqual(out["value"]["population"], 120)
        self.assertEqual(out["value"]["accounts"], 1)

    def test_tiny_population_critical_user_triggers_notify(self):
        out = self.run_service([CUSTOMERS[1]], {"A"})
        self.assertEqual(out["decision"], "notify")
        self.assertEqual(out["value"]["population"], 3)
        self.assertEqual(out["value"]["critical"], 1)

    def test_critical_user_without_population_triggers_notify(self):
        # 人口为 0 仅关键用户受影响时，仍必须通知
        out = self.run_service(
            [{"account": "PUMP-STATION", "node": "A", "critical": True, "population": 0}],
            {"A"},
        )
        self.assertEqual(out["decision"], "notify")
        self.assertEqual(out["value"], {"accounts": 1, "population": 0, "critical": 1})

    def test_only_unaffected_customers_clears(self):
        out = self.run_service([CUSTOMERS[3], CUSTOMERS[4]], {"A"})
        self.assertEqual(out["decision"], "clear")
        self.assertEqual(out["value"], {"accounts": 0, "population": 0, "critical": 0})

    def test_node_filter_remains_deterministic(self):
        # 节点筛选确定：A、B 同时停水时全部计入；仅 A 停水时 B 的用户被排除
        both = self.run_service(CUSTOMERS, {"A", "B"})
        self.assertEqual(both["value"], {"accounts": 5, "population": 824, "critical": 2})
        only_a = self.run_service(CUSTOMERS, {"A"})
        self.assertEqual(only_a["value"], {"accounts": 3, "population": 124, "critical": 1})

    def test_evaluate_directly_uses_reported_population(self):
        # 直接调用规则层（不经 normalize 注入 population_basis）也必须采用申报人口
        out = evaluate("outage_impact", payload([CUSTOMERS[0]], {"A"}))
        self.assertEqual(out["value"]["population"], 120)
        self.assertEqual(out["decision"], "notify")


if __name__ == "__main__":
    unittest.main()
