# Local Adaptive Learning

The bot uses a small tabular policy stored in `data/tribal_memory.db`. Human demonstrations contribute context/action preferences. Bot runs contribute one-step reward observations and episode scores. The model is local and inspectable; it does not use neural-network training or unrestricted action exploration.

## Import a demonstration

The video filename must contain its local recording time in the existing format. The matching logger JSONL must contain `session_start_epoch` and relative event timestamps.

```powershell
python -X utf8 process_demonstration.py "data/demonstrations/videos/2026-11-17 14-57-02.mp4" --log "data/demonstrations/logs/input_log_20261117_145657.jsonl"
```

The command prints a sync report and stores it in `demonstration_sync_reports`. Sessions with missing/mismatched logs, tracking coverage below 60%, mapped input below 15%, or time overlap below 95% remain archived but are excluded from learning. Valid samples retain the held keys, action duration, state, and confidence. The command does not upload data.

## Policy evaluation

The learner requires 20 additional eligible examples before fitting a candidate. A candidate first shadows the active policy for at least 100 state observations across two runs; its suggested actions are logged and never sent to the game. It then alternates candidate and active-policy runs, requiring at least five episodes per role. Promotion requires a score improvement of at least 5% (and at least one score point) with no meaningful increase in stuck events. If there is no promotion by ten episodes per role, the candidate is rejected. After promotion, five further episodes are monitored against the previous policy; regression or increased stuck events rolls back automatically.

Episode score is 70% target-floor progress and 30% target completion. Safety rules in `DecisionEngine` remain higher priority than learned scores.
