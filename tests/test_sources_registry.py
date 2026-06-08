"""
源适配器框架 / 注册表单元测试 —— 全离线，用 fake 适配器注入。

跑法：
    python3 -m unittest tests.test_sources_registry
"""
import unittest

from time_audit.sources.base import SourceAdapter
from time_audit.sources import registry


class _Fake(SourceAdapter):
    def __init__(self, name, events, avail=True, boom=False):
        self.name = name
        self._events = events
        self._avail = avail
        self._boom = boom

    def available(self, cfg):
        return self._avail

    def collect(self, cfg, days):
        if self._boom:
            raise RuntimeError("adapter exploded")
        return list(self._events)


def _ev(ts, content="x", app="shell"):
    return {"app": app, "content": content, "ts": ts, "source": app}


class TestCollectAll(unittest.TestCase):
    def test_merges_and_sorts_by_ts(self):
        a = _Fake("a", [_ev(30), _ev(10)])
        b = _Fake("b", [_ev(20)])
        events = registry.collect_all({}, days=7, adapters=[a, b])
        self.assertEqual([e["ts"] for e in events], [10, 20, 30])

    def test_recomputes_gap_seconds(self):
        a = _Fake("a", [_ev(100), _ev(130)])
        b = _Fake("b", [_ev(110)])
        events = registry.collect_all({}, days=7, adapters=[a, b])
        self.assertEqual(events[0]["gap_seconds"], 0)
        self.assertEqual(events[1]["gap_seconds"], 10)   # 110 - 100
        self.assertEqual(events[2]["gap_seconds"], 20)   # 130 - 110

    def test_unavailable_adapter_skipped(self):
        a = _Fake("a", [_ev(1)], avail=False)
        b = _Fake("b", [_ev(2)])
        events = registry.collect_all({}, days=7, adapters=[a, b])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 2)

    def test_failing_adapter_isolated(self):
        a = _Fake("a", [], boom=True)
        b = _Fake("b", [_ev(5)])
        # a 抛异常不应让整体挂掉，b 的事件照常返回
        events = registry.collect_all({}, days=7, adapters=[a, b])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ts"], 5)


class TestEnabledFilter(unittest.TestCase):
    def test_only_enabled_names_used(self):
        a = _Fake("shell", [_ev(1)])
        b = _Fake("screenpipe", [_ev(2)])
        cfg = {"sources": {"enabled": ["shell"]}}
        chosen = registry.enabled_adapters(cfg, all_adapters=[a, b])
        self.assertEqual([x.name for x in chosen], ["shell"])

    def test_default_enables_all_when_unset(self):
        a = _Fake("shell", [_ev(1)])
        b = _Fake("screenpipe", [_ev(2)])
        chosen = registry.enabled_adapters({}, all_adapters=[a, b])
        self.assertEqual({x.name for x in chosen}, {"shell", "screenpipe"})


if __name__ == "__main__":
    unittest.main()
