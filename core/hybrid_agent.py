# -*- coding: utf-8 -*-
"""
core/hybrid_agent.py
Autonomous Hybrid Agent (Level 3):
Kết nối toàn bộ 5 tầng kiến trúc thành vòng lặp tự động hoàn chỉnh:
Perception -> World Model -> Hybrid Decision -> Action Engine -> Persistent Memory.
"""

import time
import threading
from typing import Optional, Callable

from core.common_types import WorldState, PerceptionResult, SteeringCommand
from core.action.action_engine import ActionEngine
from core.perception.perception_engine import PerceptionEngine
from core.world.world_model import WorldModel
from core.decision.decision_engine import DecisionEngine
from core.memory.memory_manager import MemoryManager
from core.memory.strategy_updater import StrategyUpdater
from core.demonstration.behavior_prior import BehaviorPrior
from core.demonstration.demonstration_recorder import DemonstrationRecorder
from core.learning.adaptive_learner import AdaptiveLearner


class HybridAgent:
    """
    HybridAgent:
    Tác tử thông minh cấp độ 3 với bộ nhớ kinh nghiệm dài hạn.
    Tự động né cọc gỗ (Line of Sight), thoát kẹt, chọn kỹ năng và tối ưu chiến thuật.
    """

    def __init__(self, target_floor: int = 71, hp_critical_percent: float = 35.0,
                 log_callback: Optional[Callable[[str], None]] = None):
        self.target_floor = target_floor
        self.hp_critical_percent = hp_critical_percent
        self.log = log_callback or print

        # Khởi tạo 5 tầng kiến trúc
        self.action = ActionEngine()
        self.perception = PerceptionEngine()
        self.world_model = WorldModel()
        self.decision = DecisionEngine(hp_critical_percent=hp_critical_percent)
        self.memory = MemoryManager()
        self.learner = AdaptiveLearner(self.memory.db)
        self.strategy_updater = StrategyUpdater(self.memory.db)
        self.behavior_prior = BehaviorPrior()
        self.decision.steering.behavior_prior = self.behavior_prior
        self.decision.steering.adaptive_learner = self.learner
        self.recorder = DemonstrationRecorder(self.memory.db, save_screenshots=False)

        # Tải trọng số từ Memory vào Decision Engine
        w_s, w_d, w_l, w_m = self.memory.get_strategy_weights()
        self.decision.set_scoring_weights(w_s, w_d, w_l, w_m)

        self.is_running = False
        self.is_paused = False
        self._thread: Optional[threading.Thread] = None

        self.current_floor = 1
        self.stuck_counter = 0
        self.heals_counter = 0
        self.portal_step_counter = 0
        self.has_entered_room = False
        self._spawn_exit_steps_remaining = 2
        self._floor_saw_enemy = False
        self._floor_no_enemy_since = None
        self._floor_exit_completed_at = None
        self._last_combat_verify_log = 0.0
        self._portal_search_armed = False
        self._awaiting_lobby = False
        self._awaiting_game_start = False
        self._episode_has_gameplay = False
        self._end_click_attempts = 0
        self._last_end_click_time = 0.0
        self._last_lobby_click_time = 0.0
        self._lobby_click_attempts = 0
        self._last_floor_ocr_time = 0.0
        self._last_end_wait_log = 0.0

    def start(self):
        """Khởi động tác tử Hybrid Agent trong luồng riêng."""
        if self.is_running:
            return

        self.log("[HybridAgent] 🚀 Đang khởi động tác tử Autonomous Hybrid Agent...")
        if not self.action.ensure_connection():
            self.log("[HybridAgent] ❌ Không thể kết nối ADB tới BlueStacks! Vui lòng bật ADB trong Settings.")
            return False

        self.is_running = True
        self.is_paused = False
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()
        self.log(f"[HybridAgent] ✅ Đã khởi động thành công! Tầng mục tiêu: {self.target_floor}")
        return True

    def stop(self):
        """Dừng tác tử và kết thúc phiên ghi nhận."""
        self.is_running = False
        self.action.stop_all()
        # Let an in-flight perception/transition finish before closing the run.
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=4.0)
        if self.recorder.is_recording:
            self.recorder.end_session()
        if self.memory.active_run_id is not None:
            stopped_run_id = self.memory.active_run_id
            self.memory.end_run(
                reached_floor=self.current_floor,
                result="MANUAL_STOP",
                total_stuck=self.stuck_counter,
                total_heals=self.heals_counter
            )
            learning = self.learner.refresh_candidate()
            if learning.get("decision") == "REFRESHED":
                self.log(
                    f"[Learning] Candidate đã học thêm {learning['new_examples']} mẫu "
                    f"từ Run #{stopped_run_id} (tổng {learning['sample_count']}); "
                    "run dở không được tính là ván đánh giá/thăng cấp."
                )
            elif learning.get("decision") == "FROZEN_FOR_EVALUATION":
                self.log("[Learning] Run đã lưu; candidate đang được đánh giá nên giữ nguyên trọng số.")
        self.log("[HybridAgent] 🛑 Đã dừng tác tử an toàn.")

    def pause(self):
        self.is_paused = True
        self.action.stop_all()
        self.log("[HybridAgent] ⏸️ Tạm dừng.")

    def resume(self):
        self.is_paused = False
        self.log("[HybridAgent] ▶️ Tiếp tục.")

    def _reset_floor_combat_phase(self):
        self._floor_saw_enemy = False
        self._floor_no_enemy_since = None
        self._floor_exit_completed_at = None
        self.perception.reset_portal_track()
        self.world_model.reset_portal_track()
        self._last_combat_verify_log = 0.0

    def _update_floor_enemy_evidence(self, world_state, now):
        if world_state.enemies_count > 0:
            self._floor_saw_enemy = True
            self._floor_no_enemy_since = None
        elif self._floor_saw_enemy and self._floor_no_enemy_since is None:
            self._floor_no_enemy_since = now

    def _portal_search_ready(self, world_state, now):
        """Only enter portal navigation after combat evidence or a short clear check."""
        if world_state.enemies_count > 0:
            return False
        if world_state.portal is not None:
            return True
        if self.current_floor % 10 == 5:
            # Milestone floors are intentionally empty; begin route finding as
            # soon as the spawn corridor is exited instead of waiting for kills.
            return getattr(self, "_spawn_exit_steps_remaining", 0) <= 0
        if self._floor_saw_enemy:
            return (
                self._floor_no_enemy_since is not None
                and now - self._floor_no_enemy_since >= 2.4
            )
        # If no enemy was ever detected, patrol and attack briefly instead of
        # assuming the room is clear on the first empty frame.
        return (
            self._floor_exit_completed_at is not None
            and now - self._floor_exit_completed_at >= 6.0
        )

    def _main_loop(self):
        """Vòng lặp điều khiển chính của tác tử."""
        self._spawn_exit_steps_remaining = 2
        self._reset_floor_combat_phase()
        run_id = self.memory.start_run(target_floor=self.target_floor)
        self.learner.begin_episode(run_id)
        demo_session_id = self.recorder.start_session(source_type="BOT", target_floor=self.target_floor)
        self.log(f"[HybridAgent] 📝 Đã mở phiên ghi nhận Memory: Run #{run_id} | Demonstration Session #{demo_session_id}")

        last_vision_time = 0.0
        last_combat_rhythm_time = 0.0
        last_floor_check_time = 0.0
        floor_start_time = time.time()
        floor_start_hp = 100.0

        current_world_state: Optional[WorldState] = None
        current_obstacles = []
        previous_learning_state: Optional[WorldState] = None
        previous_learning_action: Optional[SteeringCommand] = None

        while self.is_running:
            if self.is_paused:
                time.sleep(0.2)
                continue

            now = time.time()

            # 1. Chu kỳ quan sát thị giác (mỗi 0.8s - 1.0s)
            if now - last_vision_time >= 0.8:
                last_vision_time = now
                frame = self.action.fast_capture_screen()
                if frame is not None:
                    # Phân tích thị giác
                    floor_check_interval = 5.0
                    check_floor = now - last_floor_check_time >= floor_check_interval
                    p_res = self.perception.analyze(frame, check_ocr_floor=check_floor)
                    if check_floor:
                        last_floor_check_time = now
                    if p_res.current_floor > self.current_floor:
                        previous_floor = self.current_floor
                        self.current_floor = p_res.current_floor
                        # Clear room-specific reward and target tracking as soon
                        # as OCR confirms a new floor, even if the portal itself
                        # was never detected before the automatic transition.
                        self._spawn_exit_steps_remaining = 2
                        self.has_entered_room = False
                        self._portal_search_armed = False
                        self._reset_floor_combat_phase()
                        self.decision.reset_portal_search()
                        p_res.portal = None
                        self.log(
                            f"[HybridAgent] 🧭 Sang tầng {previous_floor} → {self.current_floor}; "
                            "đã xóa trạng thái chiến đấu/cổng cũ và bắt đầu lại từ hành lang."
                        )
                    current_obstacles = p_res.obstacles
                    # Cập nhật World Model
                    current_world_state = self.world_model.update(p_res)
                    current_world_state.current_floor = self.current_floor
                    if current_world_state.game_state == "FIGHTING":
                        self._episode_has_gameplay = True
                        self._update_floor_enemy_evidence(current_world_state, time.monotonic())
                        if self._awaiting_game_start:
                            self._awaiting_game_start = False
                            self._lobby_click_attempts = 0
                    if previous_learning_state is not None and previous_learning_action is not None:
                        self.learner.record_transition(
                            run_id, previous_learning_state, previous_learning_action, current_world_state
                        )
                    previous_learning_state = current_world_state
                    if current_world_state.game_state == "FIGHTING":
                        self.learner.record_shadow_recommendation(run_id, current_world_state)

                    # Xử lý các trạng thái đặc biệt
                    if current_world_state.game_state == "LOBBY":
                        self.log("[HybridAgent] 🏛️ Đang ở Sảnh Chờ. Bấm Bắt Đầu / Tiếp Tục...")
                        self.has_entered_room = False
                        if self._awaiting_lobby:
                            # A new run/session only starts after the lobby is
                            # actually observed, never from a fixed delay on the end screen.
                            self.current_floor = 1
                            self.stuck_counter = 0
                            self.heals_counter = 0
                            self.portal_step_counter = 0
                            self._spawn_exit_steps_remaining = 2
                            self._reset_floor_combat_phase()
                            self.decision.reset_portal_search()
                            floor_start_hp = 100.0
                            floor_start_time = time.time()
                            run_id = self.memory.start_run(target_floor=self.target_floor)
                            self.learner.begin_episode(run_id)
                            demo_session_id = self.recorder.start_session(
                                source_type="BOT", target_floor=self.target_floor
                            )
                            previous_learning_state = None
                            previous_learning_action = None
                            self._episode_has_gameplay = False
                            self._awaiting_lobby = False
                            self._awaiting_game_start = False
                            self._lobby_click_attempts = 0
                            self.log(f"[HybridAgent] Bắt đầu lượt mới ở Sảnh: Run #{run_id} | Session #{demo_session_id}")
                        if (not self._awaiting_game_start or
                                (self._lobby_click_attempts < 3 and now - self._last_lobby_click_time >= 4.0)):
                            self.action.click_start()
                            self._awaiting_game_start = True
                            self._last_lobby_click_time = time.time()
                            self._lobby_click_attempts += 1
                            time.sleep(3.5)
                        continue

                    elif current_world_state.game_state == "LEVEL_UP":
                        self._awaiting_game_start = False
                        self.log("[HybridAgent] ⚡ Phát hiện bảng Lên Cấp. Chọn kỹ năng Thẻ 1...")
                        self.action.select_perk(1)
                        self.has_entered_room = False
                        time.sleep(0.5)
                        continue

                    elif current_world_state.game_state == "BATTLE_END":
                        if not self._awaiting_lobby:
                            detected_floor = self.perception.vision.detect_floor_number(frame)
                            if detected_floor is not None:
                                self.current_floor = max(self.current_floor, detected_floor)
                            had_gameplay = self._episode_has_gameplay or self.recorder.frame_counter > 0
                            if had_gameplay:
                                self.memory.record_floor(
                                    floor_num=self.current_floor,
                                    start_hp=floor_start_hp,
                                    end_hp=current_world_state.player_hp,
                                    duration=time.time() - floor_start_time,
                                    stuck_count=self.stuck_counter,
                                    strategy="adaptive_kiting",
                                    result="FINISHED",
                                )
                                episode_result = "SUCCESS" if self.current_floor >= self.target_floor else "FAILED"
                                self.memory.end_run(
                                    reached_floor=self.current_floor,
                                    result=episode_result,
                                    total_stuck=self.stuck_counter,
                                    total_heals=self.heals_counter,
                                    final_hp=current_world_state.player_hp,
                                )
                                learning_result = self.learner.finish_episode(
                                    run_id=run_id,
                                    reached_floor=self.current_floor,
                                    target_floor=self.target_floor,
                                    result=episode_result,
                                    safety_events=self.stuck_counter,
                                )
                                self.log(f"[Learning] Policy eval: {learning_result}")
                                self.strategy_updater.evaluate_all()
                            else:
                                self.memory.end_run(
                                    reached_floor=self.current_floor,
                                    result="NO_GAMEPLAY",
                                    total_stuck=self.stuck_counter,
                                    total_heals=self.heals_counter,
                                    final_hp=current_world_state.player_hp,
                                )
                                self.log("[HybridAgent] Bỏ qua kết quả học: màn kết thúc xuất hiện trước khi ghi nhận gameplay.")
                            if self.recorder.is_recording:
                                self.recorder.end_session(quality_score=1.0 if had_gameplay else 0.0)
                            self.has_entered_room = False
                            self._episode_has_gameplay = False
                            self._awaiting_lobby = True
                            self._end_click_attempts = 0
                            self._last_end_click_time = 0.0
                            self._last_end_wait_log = 0.0
                            self.log(
                                f"[HybridAgent] Đã ghi nhận màn kết thúc ở tầng {self.current_floor}; "
                                "đang chờ xác nhận về Sảnh trước khi mở lượt mới."
                            )

                        if (self._end_click_attempts < 3 and
                                time.time() - self._last_end_click_time >= 2.0):
                            end_coords = p_res.end_btn_coords or self.action.COORD_END_BATTLE
                            self.action.click_end_battle(end_coords)
                            self._end_click_attempts += 1
                            self._last_end_click_time = time.time()
                            self.log(
                                f"[HybridAgent] Chạm nút Kết Thúc lần {self._end_click_attempts}/3 "
                                f"tại {end_coords}; sẽ chỉ tạo lượt mới khi thấy Sảnh."
                            )
                        elif (self._end_click_attempts >= 3 and
                              time.time() - self._last_end_wait_log >= 10.0):
                            self._last_end_wait_log = time.time()
                            self.log("[HybridAgent] Vẫn ở màn kết thúc sau 3 lần chạm; giữ nguyên phiên chờ, không tạo run rỗng.")
                        continue

            # 2. Vòng lặp hành động chiến đấu & xả đạn liên tục
            if current_world_state and current_world_state.game_state == "FIGHTING":
                # Thoát khỏi hốc cửa hẹp khi xuất phát đầu tầng
                if not self.has_entered_room:
                    self.log("[HybridAgent] 🚪 Bắt đầu tầng: định hướng theo nhận diện hiện tại...")
                    self.has_entered_room = True

                # The player spawns in a narrow corridor. Exit it before
                # searching for the portal; a full directional sweep here can
                # just push into the corridor walls and return to spawn.
                if self._spawn_exit_steps_remaining > 0 and current_world_state.enemies_count == 0:
                    step_number = 3 - self._spawn_exit_steps_remaining
                    exit_cmd = SteeringCommand(
                        action_type="MOVE",
                        angle_degrees=90.0,
                        distance_ratio=1.0,
                        duration_ms=900,
                        reason=f"spawn_corridor_exit_{step_number}/2",
                    )
                    if self.recorder.is_recording:
                        self.recorder.record_frame(current_world_state, exit_cmd)
                    previous_learning_state = current_world_state
                    previous_learning_action = exit_cmd
                    self.action.move_angle_sustained(90.0, 1.0, duration_ms=1100)
                    self.log(
                        f"[HybridAgent] 🚪 Rời hành lang xuất phát: bước {step_number}/2 theo hướng 90°..."
                    )
                    self._spawn_exit_steps_remaining -= 1
                    if self._spawn_exit_steps_remaining == 0:
                        self._floor_exit_completed_at = time.monotonic()
                        self.decision.reset_portal_search()
                    continue

                # Decision Engine ra quyết định
                phase_now = time.monotonic()
                if (current_world_state.enemies_count == 0
                        and not self._portal_search_ready(current_world_state, phase_now)):
                    cmd = SteeringCommand(
                        action_type="MOVE",
                        angle_degrees=90.0,
                        distance_ratio=1.0,
                        duration_ms=1400,
                        reason="combat_clear_verification",
                    )
                    if phase_now - self._last_combat_verify_log >= 3.0:
                        self._last_combat_verify_log = phase_now
                        self.log("[HybridAgent] 🛡️ Chưa xác nhận phòng sạch; tiếp tục tuần tra trước khi tìm cổng...")
                else:
                    if (current_world_state.enemies_count == 0
                            and not self._portal_search_armed):
                        self.decision.reset_portal_search()
                        self._portal_search_armed = True
                    cmd = self.decision.decide(current_world_state, current_obstacles)
                previous_learning_state = current_world_state
                previous_learning_action = cmd

                # Ghi nhận dữ liệu thị phạm đồng bộ
                if self.recorder.is_recording:
                    self.recorder.record_frame(current_world_state, cmd)

                if cmd.action_type == "HEAL":
                    self.log(f"[HybridAgent] 🍗 {cmd.reason} -> Bơm đùi gà hồi máu!")
                    self.action.heal()
                    self.heals_counter += 1
                elif cmd.action_type == "ATTACK":
                    self.log(f"[HybridAgent] 💥 {cmd.reason} -> Quái yếu máu: Dồn hỏa lực xả đạn dứt điểm!")
                    self.action.attack()
                    time.sleep(0.04)
                    self.action.attack()
                    time.sleep(0.04)
                    self.action.attack()
                elif cmd.action_type == "MOVE":
                    if "enter_portal_cross_threshold" in cmd.reason:
                        self.log(f"[HybridAgent] 🌀 Đã chạm Cổng dịch chuyển! Bước dứt khoát qua cổng...")
                        if current_world_state.enemies_count == 0:
                            self.action.move_angle_sustained(cmd.angle_degrees, 1.0, duration_ms=1500)
                        else:
                            self.action.move_angle(cmd.angle_degrees, 1.0, duration_ms=1000)
                        self.current_floor += 1
                        self.has_entered_room = False
                        self._spawn_exit_steps_remaining = 2
                        self._reset_floor_combat_phase()
                        self.decision.reset_portal_search()
                        self.portal_step_counter = 0
                        self.log(f"[HybridAgent] 🚪 >>> ĐÃ XUYÊN QUA CỔNG! TIẾN VÀO TẦNG {self.current_floor} <<<")
                        continue
                    elif "move_to_portal" in cmd.reason:
                        if current_world_state.portal_angle is not None:
                            if self._floor_saw_enemy:
                                room_status = "Không còn thấy quái sau giao tranh"
                            else:
                                room_status = "Hết thời gian kiểm tra phòng, chưa thấy quái"
                            self.log(f"[HybridAgent] 🌀 {room_status}; đi hướng {current_world_state.portal_angle:.0f}° về cổng (cách {current_world_state.portal_dist:.0f}px)...")
                        else:
                            self.log("[HybridAgent] 🌀 Đã dọn sạch quái! Tiến thẳng lên tường đối diện (90°) tìm Cổng dịch chuyển...")
                    elif "route_floor_exploration" in cmd.reason:
                        self.log(
                            f"[HybridAgent] 🧩 Tầng mốc {self.current_floor} không có quái; "
                            f"dò lối đi hướng {cmd.angle_degrees:.0f}°..."
                        )
                    elif "portal_search_sweep" in cmd.reason:
                        self.log(f"[HybridAgent] 🧭 Chưa thấy cổng rõ; giữ hướng {cmd.angle_degrees:.0f}° để quét phòng...")
                    else:
                        self.portal_step_counter = 0

                    if "blocked_los" in cmd.reason or "stuck" in cmd.reason:
                        self.log(f"[HybridAgent] 🔄 {cmd.reason} -> Đổi góc di chuyển {cmd.angle_degrees:.0f}° để mở góc bắn!")
                        self.stuck_counter += 1
                        self.memory.record_event(
                            self.current_floor,
                            "BLOCKED_LOS_BREAKOUT",
                            current_world_state.player_pos[0],
                            current_world_state.player_pos[1],
                            cmd.reason
                        )

                    if current_world_state.enemies_count == 0:
                        # Hold each heading with a long ADB swipe; direction
                        # changes are less frequent while searching an empty room.
                        if "combat_clear_verification" in cmd.reason:
                            self.action.attack()
                        self.action.move_angle_sustained(
                            cmd.angle_degrees,
                            cmd.distance_ratio,
                            duration_ms=max(1400, cmd.duration_ms),
                        )
                    else:
                        self.action.attack()
                        time.sleep(0.04)
                        self.action.attack()
                        self.action.move_angle(cmd.angle_degrees, cmd.distance_ratio,
                                               duration_ms=cmd.duration_ms)
            else:
                time.sleep(0.1)

