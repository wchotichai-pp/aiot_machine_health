from app.rules import MachineConfig, Policy, Tracker, decide, thresholds

P = Policy(learn_samples=5, escalate_after=3, recover_after=5)


def run(cfg, tr, values, temp=30.0, t0=1000.0):
    out = []
    for i, v in enumerate(values):
        out.append(decide(cfg, tr, v, temp, t0 + i, P))
    return out


def test_default_thresholds_before_learning():
    th = thresholds(MachineConfig(), P)
    assert (th.warn, th.alarm, th.source) == (P.default_warn_rms, P.default_alarm_rms, "default")


def test_learning_sets_median_baseline_and_returns_to_monitor():
    cfg, tr = MachineConfig(mode="learning"), Tracker()
    ds = run(cfg, tr, [0.10, 0.12, 0.11, 5.0, 0.09])   # ค่ากระชาก 5.0 ไม่ทำให้ baseline เพี้ยน (median)
    assert [d.state for d in ds[:4]] == ["learning"] * 4
    assert cfg.mode == "monitor"
    assert cfg.baseline_rms == 0.11
    assert any(k == "baseline" for k, _ in ds[-1].events)


def test_min_threshold_floor_for_tiny_baseline():
    th = thresholds(MachineConfig(baseline_rms=0.01), P)
    assert th.warn == P.min_warn_rms
    assert th.alarm >= th.warn * 1.5


def test_sensitivity_changes_thresholds():
    low = thresholds(MachineConfig(baseline_rms=0.2, sensitivity="low"), P)
    high = thresholds(MachineConfig(baseline_rms=0.2, sensitivity="high"), P)
    assert high.warn < low.warn and high.alarm < low.alarm


def test_single_spike_does_not_change_state():
    cfg, tr = MachineConfig(baseline_rms=0.2), Tracker()   # warn 0.4, alarm 0.8
    ds = run(cfg, tr, [0.2, 3.0, 0.2, 0.2])
    assert all(d.state == "normal" for d in ds)
    assert "รอยืนยัน" in ds[1].reason


def test_escalate_to_alarm_then_recover_with_hysteresis():
    cfg, tr = MachineConfig(baseline_rms=0.2), Tracker()
    ds = run(cfg, tr, [1.0, 1.0, 1.0])
    assert ds[-1].state == "alarm" and ds[-1].led == "red"
    assert ds[-1].previous_state == "normal"
    ds = run(cfg, tr, [0.2] * 4)
    assert ds[-1].state == "alarm"                      # ยังไม่ครบ 5 ครั้ง
    ds = run(cfg, tr, [0.2])
    assert ds[-1].state == "normal"


def test_alarm_steps_down_to_warning():
    cfg, tr = MachineConfig(baseline_rms=0.2), Tracker()
    run(cfg, tr, [1.0] * 3)
    ds = run(cfg, tr, [0.5] * 5)                        # อยู่ระดับ warning
    assert ds[-1].state == "warning"


def test_temperature_alarm():
    cfg, tr = MachineConfig(baseline_rms=0.2), Tracker()
    ds = run(cfg, tr, [0.2] * 3, temp=60.0)
    assert ds[-1].state == "alarm"
    assert "อุณหภูมิ" in ds[-1].reason


def test_maintenance_mutes_then_expires():
    cfg, tr = MachineConfig(baseline_rms=0.2, mode="maintenance", maintenance_until=1002.5), Tracker()
    ds = run(cfg, tr, [5.0, 5.0, 5.0, 5.0])
    assert [d.state for d in ds[:3]] == ["maintenance"] * 3
    assert cfg.mode == "monitor"
    assert any(k == "mode" for k, _ in ds[3].events)
