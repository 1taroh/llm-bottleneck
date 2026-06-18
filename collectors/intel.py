import platform
import time
import subprocess
import json
import re
from .base import BaseCollector

# OSに応じたライブラリのインポート
current_os = platform.system()
if current_os == "Windows":
    try:
        import win32pdh
    except ImportError:
        raise ImportError("Windows環境でIntel iGPUを計測するには 'pip install pywin32' が必要です。")


class IntelVulkanCollector(BaseCollector):
    def __init__(self, device_index: int = 0):
        super().__init__()
        self.os_type = platform.system()
        self.device_index = device_index
        self.counters = []
        self.process = None

        # コンストラクタ全体を try-except で保護
        try:
            if self.os_type == "Windows":
                self._init_windows_pdh()
            elif self.os_type == "Linux":
                self._init_linux_intel_top()
            else:
                raise NotImplementedError(f"サポートされていないOSです: {self.os_type}")
        except Exception as e:
            # 確保しかけたリソースがあれば解放し、一塊の RuntimeError として再送出
            self.__del__()
            raise RuntimeError(f"IntelVulkanCollector の初期化に失敗しました: {e}")

    def _init_windows_pdh(self):
        """Windows用のパフォーマンスカウンター初期化"""
        self.hq = win32pdh.OpenQuery()
        # llama.cpp (Vulkan) は主に 3D または Compute エンジンを使用します
        # 複数のエンジンを統合して監視するためにワイルドカードを使用
        self.counters = []
        
        # 3Dグラフィックス負荷とCompute負荷のカウンターパスを設定
        # LUID（0x*）やGPU番号は環境に合わせて自動展開されます
        paths_to_track = [
            r"\GPU Engine(pid_*_luid_0x*_engtype_3D)\Utilization",
            r"\GPU Engine(pid_*_luid_0x*_engtype_Compute)\Utilization"
        ]
        
        for base_path in paths_to_track:
            try:
                expanded_paths = win32pdh.ExpandCounterPath(base_path)
                for path in expanded_paths:
                    # 念のためIntel系、あるいはシステム全体のカウンターを登録
                    self.counters.append(win32pdh.AddCounter(self.hq, path))
            except Exception:
                pass
                
        # 初回データ収集（カウンター初期化用）
        if self.counters:
            win32pdh.CollectQueryData(self.hq)

    def _init_linux_intel_top(self):
        """Linux用の intel_gpu_top プロセス初期化"""
        # 1秒ごとにJSON形式でGPU統計を出力するバックグラウンドプロセスを開始
        # ※ 実行環境によっては sudo 権限が必要です
        cmd = ["intel_gpu_top", "-J", "-s", "1000"]
        try:
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                bufsize=1
            )
        except FileNotFoundError:
            raise FileNotFoundError("Linux環境で計測するには 'intel-gpu-tools' (intel_gpu_top) のインストールが必要です。")

    def collect(self) -> dict:
        # ホスト側の共通メトリクスを取得（BaseCollectorのメソッドを継承）
        metrics = self.get_common_metrics()
        
        # デフォルト値の初期化
        metrics["gpu_compute_percent"] = 0.0
        metrics["vram_bandwidth_percent"] = None  # iGPUのため取得元に依存
        metrics["vram_used_gb"] = 0.0
        metrics["pcie_throughput_mbps"] = None   # メインメモリ共有のため通常は計測不可/不要

        if self.os_type == "Windows":
            metrics = self._collect_windows(metrics)
        elif self.os_type == "Linux":
            metrics = self._collect_linux(metrics)
            
        return metrics

    def _collect_windows(self, metrics: dict) -> dict:
        """Windows環境でのメトリクス収集"""
        if not self.counters:
            return metrics
            
        try:
            win32pdh.CollectQueryData(self.hq)
            total_util = 0.0
            for counter in self.counters:
                try:
                    _, val = win32pdh.GetFormattedCounterValue(counter, win32pdh.PDH_FMT_DOUBLE)
                    total_util += val
                except Exception:
                    continue
            
            # 3DとComputeの合計（最大100%に丸める）
            metrics["gpu_compute_percent"] = min(total_util, 100.0)
            
            # WindowsのiGPUのVRAM（メインメモリ共有分）は、タスクマネージャーの
            # 「専用ビデオメモリ（あれば）」＋「共有システムメモリ」からプロセスクエリ経由、
            # またはpsutilのシステムメモリ負荷などから近似する必要がありますが、
            # ここではパフォーマンスカウンターから全体のGPUメモリを取得するのは難しいため0.0としています。
            
        except Exception:
            pass
        return metrics

    def _collect_linux(self, metrics: dict) -> dict:
        """Linux環境でのメトリクス収集"""
        if not self.process or self.process.poll() is not None:
            return metrics
            
        # stdout から最新の1行（JSON）を読み取る
        # intel_gpu_top は連続してJSONブロックを流してくるため、直近のデータをパース
        line = self.process.stdout.readline()
        if not line:
            return metrics
            
        try:
            # intel_gpu_top の出力は完全に綺麗な一行JSONではない場合があるためトリム
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                
                # エンジン利用率の解析 (Render/3D/Blitterなど)
                engines = data.get("engines", {})
                render_util = engines.get("Render/3D/0", {}).get("busy", 0.0)
                video_util = engines.get("Video/0", {}).get("busy", 0.0)
                
                # llama.cppに関係するRender/3Dのbusy率を適用
                metrics["gpu_compute_percent"] = float(render_util)
                
                # メモリ帯域（IMC: インメモリコントローラ情報があれば）
                # intel_gpu_top のバージョンによって特定のキーでメモリ帯域が取れます
                if "imc-bandwidth" in data:
                    # 読み込み/書き込みのトータルなどから算出可能
                    pass 
        except Exception:
            pass
            
        return metrics

    def __del__(self):
        # リソースの解放処理
        if hasattr(self, "os_type"):
            if self.os_type == "Windows" and hasattr(self, "hq"):
                try:
                    win32pdh.CloseQuery(self.hq)
                except Exception:
                    pass
            elif self.os_type == "Linux" and hasattr(self, "process"):
                try:
                    self.process.kill()
                except Exception:
                    pass
