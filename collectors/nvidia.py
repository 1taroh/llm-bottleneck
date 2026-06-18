import pynvml
from .base import BaseCollector

class NvidiaCollector(BaseCollector):
    def __init__(self, device_index: int = 0):
        super().__init__()
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)

    def collect(self) -> dict:
        # ホスト側の共通メトリクスを取得
        metrics = self.get_common_metrics()
        
        # GPUの利用率 (演算とメモリ帯域)
        util_rates = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
        metrics["gpu_compute_percent"] = float(util_rates.gpu)
        metrics["vram_bandwidth_percent"] = float(util_rates.memory)
        
        # VRAM 容量
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        metrics["vram_used_gb"] = mem_info.used / (1024 ** 3)
        
        # PCIe スループット (TX + RX)
        try:
            pcie_tx = pynvml.nvmlDeviceGetPcieThroughput(self.handle, pynvml.NVML_PCIE_UTIL_TX_BYTES)
            pcie_rx = pynvml.nvmlDeviceGetPcieThroughput(self.handle, pynvml.NVML_PCIE_UTIL_RX_BYTES)
            metrics["pcie_throughput_mbps"] = (pcie_tx + pcie_rx) / 1024
        except pynvml.NVMLError:
            metrics["pcie_throughput_mbps"] = None

        return metrics

    def __del__(self):
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
