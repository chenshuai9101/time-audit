"""
源适配器基类。

每个数据源实现一个适配器，把各自原始数据归一化成统一事件 schema：
  {timestamp, app, window, event_type, content, file_path, source, ts}

设计原则：
  - available()：此机器上是否存在该源（不存在直接返回 False，整条管线降级）
  - collect()：返回归一化事件列表；内部异常由注册表兜底，单个源失败不影响其他源
"""
from typing import List, Dict


class SourceAdapter:
    """所有数据源适配器的基类。"""

    #: 适配器名（用于 config / CLI 开关），子类必须覆盖
    name: str = "base"

    def available(self, cfg: dict) -> bool:
        """此机器上该源是否可用。"""
        raise NotImplementedError

    def collect(self, cfg: dict, days: int) -> List[Dict]:
        """采集并归一化为统一事件列表。"""
        raise NotImplementedError
