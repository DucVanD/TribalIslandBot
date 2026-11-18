# -*- coding: utf-8 -*-
"""
core/memory/strategy_updater.py
Thực hiện Online Strategy Evaluation:
Tính toán Utility Score: U = 0.4*C + 0.3*S + 0.2*E + 0.1*T
Tự động tinh chỉnh trọng số quyết định dựa trên dữ liệu thật đã lưu.
"""

from typing import Dict, Any, Tuple
from .database import Database


class StrategyUpdater:
    """
    StrategyUpdater:
    Phân tích kết quả từ SQLite và cập nhật điểm tiện ích của từng chiến thuật.
    """

    def __init__(self, db: Database):
        self.db = db

    def evaluate_all(self) -> Dict[str, float]:
        """
        Tính toán Utility Score cho tất cả chiến thuật trong bảng strategy_stats.
        """
        scores: Dict[str, float] = {}
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT strategy_name, total_uses, success_count, avg_hp_remaining, avg_duration_sec FROM strategy_stats")
            rows = cursor.fetchall()

            for row in rows:
                name = row["strategy_name"]
                uses = row["total_uses"]
                success = row["success_count"]
                avg_hp = row["avg_hp_remaining"]
                avg_dur = row["avg_duration_sec"]

                if uses == 0:
                    c_rate = 0.5
                else:
                    c_rate = success / float(uses)

                s_rate = min(1.0, max(0.0, avg_hp / 100.0))

                # Tính toán động mức tiết kiệm tài nguyên e_rate (Resource Efficiency)
                try:
                    cursor.execute("SELECT AVG(total_heals_used) as avg_heals FROM runs WHERE result != 'RUNNING'")
                    r_stat = cursor.fetchone()
                    if r_stat and r_stat["avg_heals"] is not None:
                        avg_heals = float(r_stat["avg_heals"])
                        e_rate = max(0.2, min(1.0, 1.0 - (avg_heals / 6.0)))
                    else:
                        e_rate = 0.8
                except Exception:
                    e_rate = 0.8

                t_rate = max(0.0, min(1.0, 1.0 - (avg_dur / 100.0)))

                # Utility Score
                utility = 0.4 * c_rate + 0.3 * s_rate + 0.2 * e_rate + 0.1 * t_rate
                scores[name] = utility

                # Cập nhật ngược vào database
                cursor.execute("""
                UPDATE strategy_stats
                SET utility_score = ?, last_updated = CURRENT_TIMESTAMP
                WHERE strategy_name = ?
                """, (utility, name))

            conn.commit()
        return scores

    def recommend_weights(self) -> Tuple[float, float, float, float]:
        """
        Gợi ý bộ trọng số (w_s, w_d, w_l, w_m) dựa trên chiến thuật dẫn đầu.
        """
        scores = self.evaluate_all()
        best_strat = max(scores, key=scores.get) if scores else "adaptive_kiting"

        if best_strat == "safe_distance":
            # Ưu tiên an toàn cao
            return (0.45, 0.25, 0.20, 0.10)
        elif best_strat == "adaptive_kiting":
            # Cân bằng hoàn hảo
            return (0.35, 0.25, 0.25, 0.15)
        else:
            # Circular kiting
            return (0.30, 0.30, 0.20, 0.20)

