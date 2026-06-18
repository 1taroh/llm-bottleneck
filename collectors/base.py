from abc import ABC, abstractmethod
import psutil

class BaseCollector(ABC):
    def __init__(self):
        pass

    def get_common_metrics(self) -> dict:
        """すべての環境で共通して取得できるホスト(CPU/DRAM)のメトリクス"""
        return {
            "cpu_util_percent": psutil.cpu_percent(),
            "dram_used_gb": psutil.virtual_memory().used / (1024 ** 3)
        }

    @abstractmethod
    def collect(self) -> dict:
        """
        1回のサンプリングでデータを取得して辞書で返す。
        派生クラスはこのメソッドを実装し、get_common_metrics() の結果とマージする。
        """
        pass
