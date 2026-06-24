"""
勤務時間最適化MIP（混合整数計画）

各従業員×工程×スロットの就労有無 x[e,p,t] を決定変数とし、工程連鎖の
フロー（届いた分しか処理できない／上流の実処理が下流へラグ付きで流れる）を
線形制約で表現する。目的関数を切り替えることで案A/B/Cを統一的に解く。

これにより「誰を何時間使うか（＝高時給者を早く帰すか）」をソルバーが
締切・スキル制約込みで直接決定する。連続変数（処理量）と分数の変換係数を
扱うため CP-SAT ではなく pywraplp(CBC) を用いる。
"""
import logging
from typing import Dict, List, Optional

from .base import Assignment, _parse_time, _format_time

logger = logging.getLogger(__name__)


def _adaptive_time_limit(num_int_vars: int) -> float:
    """規模適応の時間上限（秒）。

    MIPの解時間は整数変数数に線形ではない（最悪は指数的）が、上限の
    「目安」としては変数規模に応じて伸ばすのが妥当。実際の早期終了は
    ギャップ基準（ratioGap）が担うので、これはあくまで安全弁（最悪上限）。
    5秒（小規模）〜60秒（大規模）の範囲にクランプする。
    """
    secs = 5.0 + num_int_vars / 400.0
    return max(5.0, min(60.0, secs))


def solve_mip(opt, objective_type: str,
              time_limit_sec: Optional[float] = None,
              gap_rel: float = 0.01) -> Optional[Dict[str, Dict[str, Assignment]]]:
    """
    opt: BaseOptimizer インスタンス（読み込み済みデータを利用）
    objective_type: "COST" | "MAKESPAN" | "MOVES"
    time_limit_sec: 時間上限（秒）。None なら整数変数数から規模適応で自動決定。
    gap_rel: 相対最適性ギャップの目標。最良解と下界の差がこの割合以内に
             なった時点で「実用上最適」とみなして打ち切る（既定1%）。
    戻り値: assignments、または解けない/未導入の場合 None（呼び出し側でフォールバック）
    """
    try:
        from ortools.linear_solver import pywraplp
    except ImportError:
        return None

    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        return None
    # ギャップ基準の早期終了：最適の厳密証明にこだわらず、最適から
    # gap_rel 以内と保証できた時点で止める（簡単な日は即終了、難しい日だけ粘る）。
    # CBCは SetSolverSpecificParametersAsString 非対応なので、移植性のある
    # MPSolverParameters.RELATIVE_MIP_GAP を Solve() 時に渡す。
    solver_params = pywraplp.MPSolverParameters()
    solver_params.SetDoubleParam(
        pywraplp.MPSolverParameters.RELATIVE_MIP_GAP, gap_rel
    )

    employees = opt.active_employees
    if not employees:
        return None

    slot_hours = opt.slot_hours
    rate_ot = opt.overtime_wage_rate
    threshold_slots = opt.overtime_threshold_minutes // opt.slot_minutes

    # ---- グローバルスロットグリッド（フロー伝播用の連続時間軸） ----
    slot_set = set()
    for slots in opt.employee_available_slots.values():
        slot_set.update(slots)
    for vmap in opt.root_volume.values():
        slot_set.update(vmap.keys())
    all_slots: List[str] = sorted(slot_set)
    if not all_slots:
        return None
    T = len(all_slots)
    slot_idx = {s: i for i, s in enumerate(all_slots)}
    end_min = [_parse_time(s) + opt.slot_minutes for s in all_slots]

    # ---- 昼休憩スロットを確定（既存ロジック流用）し就労不可に ----
    break_dict: Dict[str, Dict[str, Assignment]] = {e.employee_id: {} for e in employees}
    opt._assign_lunch_breaks(break_dict)
    emp_break_slots: Dict[str, set] = {
        eid: {s for s, a in d.items() if a.slot_type != "WORK"}
        for eid, d in break_dict.items()
    }

    processes = opt.process_order
    # Base capacity check (used to prune processes with 0 productivity)
    cap_base = {p: opt.base_prod.get(p, 0.0) * slot_hours for p in processes}
    # Per-employee per-process capacity (skill-adjusted)
    emp_proc_cap: Dict = {}
    for e in employees:
        eid = e.employee_id
        for p in processes:
            skill = opt.skills.get(eid, {}).get(p, 1)
            rate = opt.skill_rates.get(skill, 1.0)
            emp_proc_cap[(eid, p)] = opt.base_prod.get(p, 0.0) * rate * slot_hours
    # 各工程の唯一の上流（topo前提）
    upstream_of: Dict[str, Optional[str]] = {}
    for up, downs in opt.downstream_of.items():
        for d in downs:
            upstream_of[d] = up
    for p in processes:
        upstream_of.setdefault(p, None)

    # ---- 決定変数 x[e,p,t] ----
    x: Dict = {}
    for e in employees:
        eid = e.employee_id
        avail = set(opt.employee_available_slots.get(eid, []))
        skills = opt.skills.get(eid, {})
        brk = emp_break_slots.get(eid, set())
        for p in processes:
            if cap_base[p] <= 0 or p not in skills:
                continue
            for s in avail:
                if s in brk or s not in slot_idx:
                    continue
                x[(eid, p, s)] = solver.BoolVar(f"x_{eid}_{p}_{s}")

    if not x:
        return None

    # 規模（整数変数数）に応じた時間上限を設定（明示指定があれば優先）。
    limit_sec = time_limit_sec if time_limit_sec is not None else _adaptive_time_limit(len(x))
    solver.SetTimeLimit(int(limit_sec * 1000))

    # 1スロット1作業
    for e in employees:
        eid = e.employee_id
        for s in opt.employee_available_slots.get(eid, []):
            vs = [x[(eid, p, s)] for p in processes if (eid, p, s) in x]
            if len(vs) > 1:
                solver.Add(sum(vs) <= 1)

    # ---- 連続勤務制約：各従業員の就労は1つの連続ブロックに限定 ----
    # （遅い出勤・早い帰宅は可。途中離脱して戻る飛び地は不可。
    #   昼休憩は就労可能枠から除外済みなので午前・午後は連続扱い）
    for e in employees:
        eid = e.employee_id
        brk = emp_break_slots.get(eid, set())
        ordered = [s for s in opt.employee_available_slots.get(eid, [])
                   if s in slot_idx and s not in brk]
        ordered.sort(key=lambda s: slot_idx[s])
        # 各スロットの就労有無（0/1式）
        worked = []
        for s in ordered:
            vs = [x[(eid, p, s)] for p in processes if (eid, p, s) in x]
            worked.append(sum(vs) if vs else 0)
        # 立ち上がり（0→1への遷移）は高々1回 ＝ 連続1ブロック
        ups = []
        for i in range(len(ordered)):
            prev = worked[i - 1] if i > 0 else 0
            u = solver.NumVar(0, 1, f"up_{eid}_{i}")
            solver.Add(u >= worked[i] - prev)
            ups.append(u)
        if ups:
            solver.Add(sum(ups) <= 1)

    # ---- 処理量 proc[p,t] と フロー制約 ----
    proc: Dict = {}
    INF = solver.infinity()
    for p in processes:
        for t in range(T):
            proc[(p, t)] = solver.NumVar(0.0, INF, f"proc_{p}_{t}")

    # 能力上限： proc[p,t] <= Σ_e x[e,p,t] * (bp * skill_rate_e_p * slot_hours)
    # 各従業員の習熟レベルに応じた個別能力を係数として使う
    for p in processes:
        for t in range(T):
            s = all_slots[t]
            cap_terms = [
                emp_proc_cap[(e.employee_id, p)] * x[(e.employee_id, p, s)]
                for e in employees if (e.employee_id, p, s) in x
            ]
            if cap_terms:
                solver.Add(proc[(p, t)] <= sum(cap_terms))
            else:
                solver.Add(proc[(p, t)] <= 0)

    # 到着量 arrived[p,t]（線形式）と累積制約：届いた分しか処理できない
    def arrived_expr(p, t):
        s = all_slots[t]
        base = opt.root_volume.get(p, {}).get(s, 0.0)
        expr = base
        up = upstream_of.get(p)
        if up is not None and t - 1 >= 0:
            expr = expr + opt.conv_rate.get(p, 1.0) * proc[(up, t - 1)]
        return expr

    for p in processes:
        cum_proc = 0
        cum_arr = 0
        for t in range(T):
            cum_proc = cum_proc + proc[(p, t)]
            cum_arr = cum_arr + arrived_expr(p, t)
            solver.Add(cum_proc <= cum_arr)
        # 全量処理（最終スロットで在庫ゼロ）
        solver.Add(cum_proc >= cum_arr)

    # ---- 締切：期限スロット以降は処理不可、かつ期限までに到着分を処理 ----
    for p, dl in opt.deadlines.items():
        if cap_base.get(p, 0.0) <= 0:
            continue
        dmin = _parse_time(dl)
        cum_proc = 0
        cum_arr = 0
        for t in range(T):
            if end_min[t] > dmin:
                solver.Add(proc[(p, t)] == 0)
            cum_proc = cum_proc + proc[(p, t)]
            cum_arr = cum_arr + arrived_expr(p, t)
            if end_min[t] == dmin or (t + 1 < T and end_min[t] <= dmin < end_min[t + 1]):
                solver.Add(cum_proc >= cum_arr)

    # ---- 残業：n_e, ot_e ----
    n_var, ot_var = {}, {}
    for e in employees:
        eid = e.employee_id
        my = [x[k] for k in x if k[0] == eid]
        n = solver.NumVar(0, len(my), f"n_{eid}")
        solver.Add(n == (sum(my) if my else 0))
        ot = solver.NumVar(0, len(my), f"ot_{eid}")
        solver.Add(ot >= n - threshold_slots)
        n_var[eid] = n
        ot_var[eid] = ot

    cost_expr = 0
    for e in employees:
        eid = e.employee_id
        w = float(e.hourly_wage) * slot_hours
        cost_expr = cost_expr + w * n_var[eid] + w * (rate_ot - 1.0) * ot_var[eid]

    # ---- 目的関数 ----
    if objective_type == "COST":
        solver.Minimize(cost_expr)
    elif objective_type == "MAKESPAN":
        M = solver.NumVar(0, max(end_min), "M")
        for (eid, p, s), var in x.items():
            solver.Add(M >= end_min[slot_idx[s]] * var)
        # 完了時刻最小化、コストは微小重みで二次目的
        solver.Minimize(M * 10000.0 + cost_expr)
    elif objective_type == "MOVES":
        # 工程分散の代理指標：従業員が触れる工程数 - 就労有無
        y, w_emp = {}, {}
        for e in employees:
            eid = e.employee_id
            worked = solver.BoolVar(f"w_{eid}")
            w_emp[eid] = worked
            for p in processes:
                ks = [x[(eid, p, s)] for s in all_slots if (eid, p, s) in x]
                if not ks:
                    continue
                yp = solver.BoolVar(f"y_{eid}_{p}")
                for v in ks:
                    solver.Add(yp >= v)
                solver.Add(worked >= yp - 0)  # worked is 1 if any process used
                y[(eid, p)] = yp
        moves_expr = sum(y.values()) - sum(w_emp.values())
        solver.Minimize(moves_expr * 10000.0 + cost_expr)
    else:
        solver.Minimize(cost_expr)

    status = solver.Solve(solver_params)

    # ---- ステータス・ギャップのログ出力 ----
    # OPTIMAL: 時間内に厳密最適を証明 → 時間は余っている（上限を下げてよい）
    # FEASIBLE: 時間切れで打ち切り。実用解はあるが最適の証明はできていない
    #           → 残ギャップ(%)が「どれだけ最適から妥協したか」を表す
    status_name = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }.get(status, str(status))

    wall_sec = solver.wall_time() / 1000.0
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        gap = None
        try:
            obj_val = solver.Objective().Value()
            best_bound = solver.Objective().BestBound()
            gap = abs(obj_val - best_bound) / (abs(obj_val) + 1e-10)
            logger.info(
                "MIP[%s] status=%s gap=%.2f%% obj=%.1f bound=%.1f "
                "int_vars=%d time_limit=%.1fs wall=%.2fs",
                objective_type, status_name, gap * 100.0, obj_val, best_bound,
                len(x), limit_sec, wall_sec,
            )
        except Exception:
            logger.info("MIP[%s] status=%s (gap計算不可)", objective_type, status_name)
        # 画面の「計算ログ」に表示するため最適化インスタンスへ記録
        opt.last_solve_meta = {
            "status": status_name, "gap": gap, "seconds": wall_sec,
        }
    else:
        logger.warning(
            "MIP[%s] status=%s 解なし→ヒューリスティックへフォールバック",
            objective_type, status_name,
        )
        opt.last_solve_meta = {
            "status": status_name, "gap": None, "seconds": wall_sec,
        }
        return None

    # 探索ノード数を検証パターン数として加算
    try:
        opt.patterns_evaluated += int(solver.nodes())
    except Exception:
        pass

    # ---- 解を assignments へ ----
    assignments: Dict[str, Dict[str, Assignment]] = {e.employee_id: {} for e in employees}
    # 休憩を戻す
    for eid, d in break_dict.items():
        for s, a in d.items():
            if a.slot_type != "WORK":
                assignments[eid][s] = a
    for (eid, p, s), var in x.items():
        if var.solution_value() > 0.5:
            emp = next(e for e in employees if e.employee_id == eid)
            is_ot = opt._is_overtime_slot(emp, s, assignments[eid])
            cost = opt._calc_slot_cost(emp, s, assignments[eid])
            assignments[eid][s] = Assignment(
                employee_id=eid, process_id=p, time_slot_start=s,
                slot_type="WORK", is_overtime=is_ot, slot_cost=cost,
            )
    return assignments
