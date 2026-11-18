# IMPLEMENTATION ROADMAP & PHASE SPECIFICATION (P1–P8)
## TribalIslandBot – Incremental Evolution from Reactive Bot to Autonomous Hybrid Agent

> **Document Version:** 1.0  
> **Architecture Target:** Level 3 Autonomous Hybrid Agent  
> **Last Updated:** 2026-11-17  
> **Status:** APPROVED FOR STAGED EXECUTION  

---

## 1. Executive Summary & Delivery Strategy

The evolution of TribalIslandBot is structured into an **8-Phase Incremental Delivery Plan (P1–P8)**. Rather than undertaking a high-risk, full-system rewrite, this roadmap enforces a strict "wrap-and-verify" methodology:
- Existing, functional modules (`ActionEngine`, `PerceptionEngine`, `WorldModel`, `DecisionEngine`, `Database`) are preserved and verified as the reliable baseline.
- New capabilities (Demonstration Recording, Behavioral Segmentation, Conditional Replay, Procedural Memory) are layered on top via clear contracts without breaking existing combat loops.
- Each phase concludes with an executable test suite and strict Pass/Fail acceptance gates before subsequent phases commence.

---

## 2. Phase Dependency Graph (DAG)

```mermaid
flowchart TD
    classDef existing fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef inprog fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef planned fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;

    P1[P1: Unified Action Engine<br/>ADB fast-capture & analog swipe]::existing
    P5[P5: Perception & World Model<br/>Detectors, LOS, spatial model]::existing
    
    P1 --> P2[P2: Demonstration Recorder<br/>Synchronized State + Action logger]::planned
    P5 --> P2
    
    P2 --> P3[P3: Behavior Segmentation<br/>Phase detection: Approach/Combat/Retreat]::planned
    
    P3 --> P4[P4: Conditional Strategy Replay<br/>Precondition matching & abort guard]::planned
    P5 --> P4
    
    P1 --> P6[P6: Hybrid Decision Engine<br/>4-tier hierarchy: Safety->Tactical->Replay->Score]::inprog
    P4 --> P6
    P5 --> P6
    
    P6 --> P7[P7: Long-Term Memory & Adaptive<br/>Procedural memory, DB migration, weight updater]::planned
    
    P1 --> P8[P8: Full System Integration<br/>RunManager lifecycle, GUI, end-to-end runs]::planned
    P6 --> P8
    P7 --> P8
```

---

## 3. Detailed Phase Breakdown (P1 – P8)

### Phase P1: Unified Action Engine
- **Objective:** Establish the sole physical execution gateway into BlueStacks via ADB; eliminate all dependencies on `pydirectinput` and OS mouse/keyboard hijacking.
- **Existing Assets Leveraged:** `core/action/action_engine.py`, `core/engine_adb.py`.
- **New Deliverables:** Action command queue pattern, thread-safe capture wrapper, reconnect health monitor.
- **Affected Data Contracts:** `SteeringCommand`, `ActionCommand`.
- **Database Changes:** None.
- **Complexity:** Medium (Already ~85% implemented in source).
- **Acceptance Gate:** `tests/test_p1_action.py` passes 100%. Frame capture $< 100\text{ ms}$. 30-second continuous background input test with zero host focus theft.

---

### Phase P2: Demonstration Recorder
- **Objective:** Implement non-intrusive, synchronized recording of human demonstration gameplay sessions.
- **Existing Assets Leveraged:** `core/demonstration/trajectory_extractor.py`, `ActionEngine.fast_capture_screen()`.
- **New Deliverables:** `core/demonstration/demonstration_recorder.py`, session management, screenshot-to-state synchronization buffer.
- **Affected Data Contracts:** `DemonstrationFrame`, `DemonstrationSession`.
- **Database Changes:** Add `demonstration_sessions` and `demonstration_frames` tables to `tribal_memory.db`.
- **Complexity:** Medium-High.
- **Acceptance Gate:** Record 5 minutes of live play. 100% of recorded frames contain paired `WorldState`, timestamp, and detected touch event with zero frame drops.

---

### Phase P3: Behavior Segmentation
- **Objective:** Automatically segment continuous demonstration streams into tactical phases: `APPROACH`, `COMBAT`, `RETREAT`, `STUCK_RECOVERY`.
- **Existing Assets Leveraged:** Trajectory data from P2, `core/perception/detector_enemy.py`.
- **New Deliverables:** `core/demonstration/behavior_segmenter.py`, phase classification heuristics.
- **Affected Data Contracts:** `BehaviorSegment`, `PhaseType`.
- **Database Changes:** Add `behavior_segments` table.
- **Complexity:** Medium.
- **Acceptance Gate:** Correctly classify known gameplay phases with $\ge 90\%$ accuracy against ground truth annotations.

---

### Phase P4: Conditional Strategy Replay
- **Objective:** Replay demonstrated behavioral sequences only when environmental preconditions match, protected by active abort monitors.
- **Existing Assets Leveraged:** `core/demonstration/behavior_prior.py`.
- **New Deliverables:** `core/demonstration/conditional_replayer.py`, precondition matcher, abort monitor.
- **Affected Data Contracts:** `StrategyCandidate`, `ReplayPrecondition`, `AbortCondition`.
- **Database Changes:** Add `strategy_candidates` table.
- **Complexity:** High.
- **Acceptance Gate:** Bot replays demonstration safely; immediately aborts to Safety Rules within $< 100\text{ ms}$ if HP drops by $> 15\%$.

---

### Phase P5: Perception & World State Enhancement
- **Objective:** Refactor spatial modeling, eliminate dead code, and formalize line-of-sight and obstacle evasion.
- **Existing Assets Leveraged:** `core/perception/perception_engine.py`, `core/world/world_model.py`, `core/perception/line_of_sight.py`.
- **New Deliverables:** Resolution of `StuckDetector` duplicate; cleanup of `stuck_start_time` dead code; validation of `stump_sample.png`.
- **Affected Data Contracts:** `PerceptionResult`, `WorldState`, `Entity`.
- **Database Changes:** None.
- **Complexity:** Low-Medium.
- **Acceptance Gate:** `tests/test_p3_world_model.py` and `tests/test_p2_perception.py` pass. Detection confidence $\ge 95\%$ on reference suite.

---

### Phase P6: Hybrid Decision Engine Formalization
- **Objective:** Implement the full 4-tier decision hierarchy (Safety $\rightarrow$ Tactical $\rightarrow$ Demonstration $\rightarrow$ Scoring).
- **Existing Assets Leveraged:** `core/decision/decision_engine.py`, `core/decision/safety_rules.py`, `core/navigation/vector_steering.py`.
- **New Deliverables:** Tier 3 integration hook, strict single-ownership arbiter.
- **Affected Data Contracts:** `SteeringCommand`, `DecisionContext`.
- **Database Changes:** None.
- **Complexity:** Medium.
- **Acceptance Gate:** Safety override fires 100% of times when $HP < 35\%$ or enemy $< 160\text{ px}$, preempting any active replay.

---

### Phase P7: Long-Term Memory & Adaptive Learning
- **Objective:** Implement Procedural Memory (the 4th memory tier), strategy lifecycle versioning, automated DB migrations, and dynamic utility scoring.
- **Existing Assets Leveraged:** `core/memory/database.py`, `core/memory/memory_manager.py`, `core/memory/strategy_updater.py`.
- **New Deliverables:** `ProceduralMemory` manager, dynamic $E$-rate calculation in `StrategyUpdater`, DB backup & migration engine.
- **Affected Data Contracts:** `ProceduralPattern`, `StrategyLifecycleState`.
- **Database Changes:** Add `procedural_patterns` and `schema_migrations` tables; add WAL mode and indexes.
- **Complexity:** High.
- **Acceptance Gate:** System persists 10 runs, updates strategy utility scores dynamically, and successfully executes automatic rollback to baseline within $< 10\text{ ms}$ upon simulated degradation.

---

### Phase P8: Full System Integration & Extended Operations
- **Objective:** Unify all layers into `HybridAgent` and `RunManager`, providing robust GUI monitoring and 5-run autonomous operation.
- **Existing Assets Leveraged:** `core/hybrid_agent.py`, `core/manager_run.py`, `gui/app_window.py`, `main.py`.
- **New Deliverables:** Deprecation of legacy `CombatEngine` code paths; run lifecycle watchdog.
- **Affected Data Contracts:** All.
- **Database Changes:** None.
- **Complexity:** Medium-High.
- **Acceptance Gate:** Bot autonomously runs 5 complete cycles (Lobby $\rightarrow$ Target Floor $\rightarrow$ Suicide/Exit $\rightarrow$ Loot $\rightarrow$ Lobby) without human intervention, crash, or memory leak.

---

## 4. Technical Risk Register

| Risk ID | Category | Risk Description | Severity | Probability | Mitigation Strategy |
|---|---|---|---|---|---|
| **R-01** | Input | ADB command latency spikes during heavy screen animations | High | Med | Use binary `exec-out` for capture; use background ADB batch pipes; fallback to tap keepalive. |
| **R-02** | Decision | Replay execution gets trapped in unpredicted obstacle geometry | High | Med | Abort condition triggers if character position delta $< 30\text{ px}$ over $1.0\text{ s}$, handing control to Stuck Recovery. |
| **R-03** | Safety | Demonstration model issues movement into monster pack | Critical | Low | Tier 1 Safety Rules evaluate *after* replayer proposal and possess absolute veto power. |
| **R-04** | Memory | Database corruption on sudden emulator or host crash | High | Low | Enable SQLite WAL mode (`PRAGMA journal_mode=WAL`), maintain hourly automated database snapshots. |
| **R-05** | Perception | Character detection failure due to spell visual FX | Med | Med | Fallback to Kalman/last-known position tracking; lower confidence triggers elliptical safety kiting. |
| **R-06** | Learning | Overfitting to single human demonstration style | Med | High | BehaviorPrior provides soft scoring bonus ($\le 15\%$), never rigid deterministic playback without preconditions. |
| **R-07** | Concurrency | Deadlock between vision capture thread and actuation thread | High | Low | Single fine-grained lock on ADB socket channel; timeout ceiling of $5\text{ s}$ on all subprocess calls. |
| **R-08** | Storage | Video and screenshot assets consume excessive disk space | Med | Med | Downsample demonstration frames to $960\times 540$; delete raw images after trajectory vector extraction. |
| **R-09** | Architecture| Dual control path regression re-introduces `pydirectinput` | High | Low | Formal deprecation of `CombatEngine`; CI assertion ensuring no `pydirectinput` imports in active paths. |
| **R-10** | Game | Target floor reached but character fails to suicide promptly | Low | Low | Suicide mode explicitly turns off attack loop, locks movement, and waits for HP to reach 0. |

---

## 5. Pre-Implementation Checklist (Questions to Verify)

Before writing any new implementation code:
1. **ADB Device Identification:** Confirm if BlueStacks port `5555` is consistently mapped or if multiple instances require dynamic ADB port detection.
2. **Missing Asset:** Acquire or crop `assets/stump_sample.png` to ensure `HazardDetector` template matching operates at peak precision.
3. **Legacy CombatEngine Deprecation:** Confirm whether legacy `CombatEngine` should be moved to `archive/` or retained strictly as an emergency offline testbed.
4. **Demonstration Dataset:** Determine how many human demonstration MP4 videos are ready for ingestion into `TrajectoryExtractor` (currently 4 videos identified in `data/demonstrations/videos/`).
5. **Database Migration Safety:** Verify that `data/tribal_memory.db` backup is created before running any DDL table additions.

