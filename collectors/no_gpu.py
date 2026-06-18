from .base import BaseCollector

class NoGpuCollector(BaseCollector):
    def collect(self) -> dict:
        # ホスト側の共通メトリクスのみ取得
        metrics = self.get_common_metrics()
        
        # GPU関連のフィールドは構造維持のために None で埋める
        metrics["gpu_compute_percent"] = None
        metrics["vram_bandwidth_percent"] = None
        metrics["vram_used_gb"] = None
        metrics["pcie_throughput_mbps"] = None
        
        return metrics
