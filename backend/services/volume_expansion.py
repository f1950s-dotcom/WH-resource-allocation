"""
物量展開サービス（シンプル方式）

考え方:
  - 展開するのは「入庫/出庫ラインの最初の工程（根元工程）」のみ。
  - 各根元工程の作業量 = 登録物量 × その工程の変換係数。
  - 計上は物量が登録されたスロットのみ。累積（キャリーオーバー）は行わない。
  - 下流工程（棚入など）は、実際にいつ作業が発生するか配置に依存するため、
    ここでは展開しない。
  - 例) 入庫100, 入庫→入荷=0.5 なら 入荷の作業発生=50。
        基準生産性15個/人時, 15分スロットなら必要人員 = 50 / (15 * 0.25) = 13.3。
"""
from datetime import datetime
import uuid
from typing import Dict, List

from sqlalchemy.orm import Session

from models import VolumePlan, VolumeConversionRule, VolumeExpansion, Process, ProcessConnection


def expand_volume(plan_date: str, db: Session) -> List[VolumeExpansion]:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    plans = db.query(VolumePlan).filter(VolumePlan.plan_date == plan_date).all()
    if not plans:
        return []

    # 変換係数: process_id -> (source_type, rate)
    rules = db.query(VolumeConversionRule).all()
    rule_map: Dict[str, tuple] = {
        r.process_id: (r.source_type, float(r.conversion_rate)) for r in rules
    }

    active_processes = {
        p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()
    }
    if not active_processes:
        return []

    # 工程接続: 下流 -> 上流。下流工程の集合（=根元でない工程）を作る
    connections = db.query(ProcessConnection).all()
    downstream_pids = {c.to_process_id for c in connections}

    # 根元工程 = 接続の下流側になっていない工程
    root_pids = [pid for pid in active_processes if pid not in downstream_pids]

    slot_duration_hours = 15.0 / 60.0

    db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == plan_date).delete()

    expansions: List[VolumeExpansion] = []

    for plan in plans:
        volume = float(plan.volume)
        slot = plan.time_slot_start

        for pid in root_pids:
            rule = rule_map.get(pid)
            if not rule:
                continue
            source_type, rate = rule
            # この物量(入庫/出庫)に対応する根元工程のみ展開
            if source_type != plan.volume_type:
                continue

            proc = active_processes[pid]
            bp = float(proc.base_productivity)

            process_volume = volume * rate
            required_person_slots = (
                process_volume / (bp * slot_duration_hours) if bp > 0 else 0.0
            )

            exp = VolumeExpansion(
                expansion_id=str(uuid.uuid4()),
                plan_date=plan_date,
                process_id=pid,
                time_slot_start=slot,
                process_volume=round(process_volume, 2),
                carry_over_volume=0.0,
                required_person_slots=round(required_person_slots, 3),
                calculated_at=now,
            )
            db.add(exp)
            expansions.append(exp)

    db.commit()
    for e in expansions:
        db.refresh(e)

    return expansions
