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

from .base import Assignment, _parse_time

logger = logging.getLogger(__name__)


def _adaptive_time_limit(num_int_vars: int) -> float:
    """規模適応の時間上限（秒）。

    MIPの解時間は整数変数数に線形ではない（最悪は指数的）が、上限の
    「目安」としては変数規模に応じて伸ばすのが妥当。実際の早期終了は
    ギャップ基準（ratioGap）が担うので、これはあくまで安全弁（最悪上限）。
    5秒（小規模）〜60秒（大規模）の範囲にクランプする。
    """
    secs = 5.0 + num_int_vars / 150.0
    return max(5.0, min(300.0, secs))


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

    # ---- 最低勤務時間：配置するなら一定時間以上働かせる（0=無効） ----
    # 各従業員の総就労スロット n_e は 0 か min_slots 以上のいずれか。
    # これにより「短時間だけ呼び出す」配置を排除する（出社させない＝除外）。
    min_work_slots = getattr(opt, "min_work_minutes", 0) // opt.slot_minutes
    if min_work_slots > 0:
        for e in employees:
            eid = e.employee_id
            my = [x[k] for k in x if k[0] == eid]
            if not my:
                continue
            worked_emp = solver.BoolVar(f"worked_{eid}")
            solver.Add(sum(my) <= len(my) * worked_emp)
            solver.Add(sum(my) >= min_work_slots * worked_emp)

    # ---- 工程移動ペナルティ変数 pen[e,p,t] ----
    # pen[e,p,t]=1 は「従業員eがスロットtで工程pに就労かつ直前スロットに
    # 別工程で就労していた」ことを表す（＝移動直後スロット）。
    # x[e,p,t] と other[e,p,t-1]=Σ_{p2≠p} x[e,p2,t-1] の積をMcCormick
    # 線形化（product of two [0,1] vars）で表現する。
    pen: Dict = {}
    penalty_enabled = getattr(opt, "transition_penalty_enabled", False)
    penalty_rate = getattr(opt, "transition_penalty_rate", 0.30)
    if penalty_enabled and penalty_rate > 0:
        for (eid, p, s), xvar in x.items():
            t = slot_idx[s]
            if t == 0:
                continue
            s_prev = all_slots[t - 1]
            # 前スロットで別工程に就労していた場合にのみペナルティが発生
            other_terms = [
                x[(eid, p2, s_prev)]
                for p2 in processes if p2 != p and (eid, p2, s_prev) in x
            ]
            if not other_terms:
                continue
            pen_var = solver.BoolVar(f"pen_{eid}_{p}_{t}")
            other_sum = sum(other_terms)
            # McCormick: pen = x * other_sum  (both in [0,1])
            solver.Add(pen_var <= xvar)
            solver.Add(pen_var <= other_sum)
            solver.Add(pen_var >= xvar + other_sum - 1)
            pen[(eid, p, s)] = pen_var

    # ---- 処理量 proc[p,t] と フロー制約 ----
    proc: Dict = {}
    INF = solver.infinity()
    for p in processes:
        for t in range(T):
            proc[(p, t)] = solver.NumVar(0.0, INF, f"proc_{p}_{t}")

    # 能力上限： proc[p,t] <= Σ_e x[e,p,t] * cap - Σ_e pen[e,p,t] * cap * penalty_rate
    # ペナルティが有効な場合は移動直後スロットの容量を減額する
    for p in processes:
        for t in range(T):
            s = all_slots[t]
            cap_terms = []
            for e in employees:
                eid = e.employee_id
                if (eid, p, s) not in x:
                    continue
                cap = emp_proc_cap[(eid, p)]
                term = cap * x[(eid, p, s)]
                if (eid, p, s) in pen:
                    term = term - cap * penalty_rate * pen[(eid, p, s)]
                cap_terms.append(term)
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

    # 全量処理は「ソフト制約」にする。
    #   旧実装は cum_proc >= cum_arr（全量処理）をハード制約にしていたため、
    #   容量・締切が厳しい日（特に工程移動ペナルティで実効容量が下がる日）に
    #   MIPがINFEASIBLEになり「MIP解なし」へ転落していた。一方ヒューリスティックは
    #   処理しきれない分を残務として報告するだけで必ず解を返す。両者の前提を
    #   揃えるため、未処理量 short_p を許容し、目的関数で非常に重く罰する。
    #   これで MIP は常に実行可能解を持ち（最悪でも全スロット非稼働＝空解が成立）、
    #   かつヒューリスティックの選択肢を包含するため解の質は決して下回らない。
    #
    # 【最低配置時間（1工程の最低連続配置）はMIPに入れない】
    # 「一度入った工程に最低◯分連続で就く」というハード制約は整数変数の
    # 組合せ爆発を招き、CBCが時間制限を無視して暴走したり数値例外で
    # クラッシュしたりして、実データでは事実上解けなくなる（全案が簡易計算に
    # 落ちる）ことが判明した。そこで方針を変更し、MIPには入れず、解が
    # 出来た後に「同一スロット内で工程ラベルを入れ替える」連続化リペア
    # （_repair_continuity）で細切れ切替を後処理で減らす。リペアは各工程の
    # スロット別人数（＝処理量・完了時刻・コスト）を一切変えないため、
    # 最適解の質を保ったまま15分単位の無意味な工程切替だけを解消できる。
    short_terms = []
    # 各時刻の滞留量（cum_arr - cum_proc）の総和。MAKESPAN目的で使う。
    # この「在庫時間」を最小化すると、届いた物量を可能な限り早く処理する解に
    # なり、実質的に全体の完了時刻（makespan）が最小化される。連続変数のみで
    # 緩和が強く、big-M型のM変数よりCBCが圧倒的に速く解ける。
    inventory_terms = []
    for p in processes:
        cum_proc = 0
        cum_arr = 0
        for t in range(T):
            cum_proc = cum_proc + proc[(p, t)]
            cum_arr = cum_arr + arrived_expr(p, t)
            # 届いた分しか処理できない（物理制約・ハードのまま）
            solver.Add(cum_proc <= cum_arr)
            # 時刻tでの未処理滞留（>=0）。早く処理するほど小さくなる。
            inventory_terms.append(cum_arr - cum_proc)
        short_p = solver.NumVar(0.0, INF, f"short_{p}")
        solver.Add(short_p >= cum_arr - cum_proc)  # 未処理量（最終時点）
        short_terms.append(short_p)

    # ---- 締切（must_finish_by）はハード打ち切りにしない ----
    #   旧実装は「締切時刻以降は当該工程の処理＝0」を課していた。これだと
    #   定時(17:00)までに終わらない最終工程（棚入れ・梱包）を、残業枠
    #   (17:00〜20:00)が人員的に空いていても処理できず、残務を残して
    #   帰す挙動になっていた。
    #
    #   運用方針は3段階の優先順位：
    #     ① 残業なし（定時内）で入出庫の最終工程まで全て終わらせる
    #     ② 終わらなければ残業して残業最大終了時刻(20:00)までにやり切る
    #        （残業不可の人は残業枠に配置しない＝availableスロットで担保済み）
    #     ③ それでも無理なら作業残を残して帰る
    #   これを実現するため、締切はハード制約として課さず、処理可能範囲は
    #   各従業員のavailableスロット（残業可否を反映済み）にのみ委ねる。
    #   ・①は目的関数が残業割増(cost_expr)を嫌うため自然に成立
    #   ・②は未処理ペナルティ(short)が残業コストより桁違いに重いため成立
    #   ・③はshortとして許容（最後の逃げ道）
    #   締切時刻(17:00)は「残業なしで間に合ったか」のKPIとして calc_score の
    #   is_deadline_met / deadline_violations の判定には引き続き用いる（表示のみ）。
    #
    #   ただし「なるべく定時内に終わらせる（①）」を成立させるため、締切時刻
    #   以降に行う処理量に対してソフトな late ペナルティを課す。コスト目的は
    #   完了時刻に無関心なので、これが無いと（コストが同じなら）作業を夕方〜
    #   20:00へ無意味に引き延ばす解が選ばれてしまう。重み階層は
    #       残務(short) ≫ 締切後処理(late) ≫ 残業割増 ≫ 通常コスト
    #   とし、(a)定時内完了を最優先、(b)定時で無理なら締切後処理＝実質残業で
    #   やり切る、(c)それも無理なら残務、の順に選ばれるようにする。
    late_terms = []
    for p, dl in opt.deadlines.items():
        if cap_base.get(p, 0.0) <= 0:
            continue
        dmin = _parse_time(dl)
        for t in range(T):
            if end_min[t] > dmin:
                late_terms.append(proc[(p, t)])
    sum_late = sum(late_terms) if late_terms else 0

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

    # 未処理量ペナルティ。
    # 重み選択の根拠：未処理1単位でもどの目的より重くする必要があるが、
    # 係数が大きすぎるとCBCの数値精度が悪化しNOT_SOLVEDになる。
    # 目的別に「その目的の最大スケール」を上回る最小限の重みを使う。
    sum_short = sum(short_terms) if short_terms else 0

    # ---- 目的関数 ----
    if objective_type == "COST":
        # 重み階層：残務(1e5) ≫ 締切後処理(1e3) ≫ 残業割増(cost_expr内) ≫ 通常コスト。
        #  - sum_late は「定時(17:00)以降に最終工程を処理した量」。コスト目的は
        #    完了時刻に無関心なため、これが無いと作業を夕方へ無意味に引き延ばす
        #    解が選ばれる。1e3 により「定時内で終わるなら終わらせる」を優先しつつ、
        #    残務(1e5)よりは軽いので「残務を残すより残業してでも終わらせる」も成立。
        #  - 全量が定時内に収まる通常日は sum_late=0 となり、純粋なコスト最小化に戻る。
        solver.Minimize(cost_expr + 1.0e3 * sum_late + 1.0e5 * sum_short)
    elif objective_type == "MAKESPAN":
        # 「最遅スロットを最小化」する連続変数M＋big-M制約は緩和が弱く、
        # CBCが整数解を1つも見つけられずNOT_SOLVEDになっていた。また
        # 「終了時刻で重み付けした総和」では人数が少ない遅い解の方が安くなり
        # makespanの代理にならなかった。
        # 正しくは各時刻の滞留量の総和（在庫時間）を最小化する。届いた物量を
        # 早く処理するほど滞留が早く消えて総和が小さくなるため、完了時刻が
        # 最小化される。連続変数のみで緩和が強く高速。
        inventory_expr = sum(inventory_terms) if inventory_terms else 0
        # 在庫時間を最優先、コストは同点をほぐす微小二次目的。
        # 未処理ペナルティは在庫時間より十分大きく（在庫の上限を上回る）。
        solver.Minimize(inventory_expr + cost_expr * 0.001 + 1.0e8 * sum_short)
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
        solver.Minimize(moves_expr * 10000.0 + cost_expr + 1.0e8 * sum_short)
    else:
        solver.Minimize(cost_expr + 1.0e5 * sum_short)

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

    # LP反復回数 + B&Bノード数を検証パターン数として加算
    # nodes()=0はLP緩和で一発整数解が得られたことを意味する（正常）。
    # iterations()はシンプレックス反復で実際の探索量を表す。
    try:
        opt.patterns_evaluated += int(solver.iterations()) + int(solver.nodes())
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


# ---------------------------------------------------------------------------
# プロセス隔離つきMIP求解
# ---------------------------------------------------------------------------
# CBCソルバーは min_process（連続配置）制約のような数値的に厳しいモデルで、
#   (1) SetTimeLimit を無視して暴走する（10分以上）
#   (2) 内部数値矛盾で CoinError を投げ、C++層で abort してプロセス即死する
# という非決定的な異常を起こす。いずれも通常の try/except では止められない
# （特に abort は捕捉不能）。そこで MIP の求解を「使い捨ての子プロセス」で実行し、
# 親（＝バックエンド本体）から
#   - ハードな実時間上限で子を強制終了（暴走対策）
#   - 子が abort で死んでも親は生存（クラッシュ隔離）
# できるようにする。子が時間内に解を返せなければ None を返し、呼び出し側の
# ヒューリスティックにフォールバックする。

def _mip_worker(module_name: str, class_name: str, plan_date: str,
                method: str, objective_type: str, q) -> None:
    """子プロセス側エントリ。DBから最適化器を再構築して solve_mip を実行する。"""
    try:
        import importlib
        from database import SessionLocal, engine
        # fork で親のDB接続プールを引き継ぐとSQLite接続が壊れるため、
        # 子側で破棄して新しい接続を張り直す。
        engine.dispose()
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        db = SessionLocal()
        try:
            opt = cls(plan_date, db, method)
            res = solve_mip(opt, objective_type)
            q.put(("ok", res, opt.last_solve_meta, opt.patterns_evaluated))
        finally:
            db.close()
    except Exception as e:  # Python層で捕捉できた例外はフォールバック扱いで返す
        q.put(("err", None,
               {"status": f"EXCEPTION:{type(e).__name__}", "gap": None, "seconds": 0.0},
               0))


def solve_mip_isolated(opt, objective_type: str,
                       hard_timeout_sec: float = 420.0):
    """solve_mip を子プロセスで実行し、暴走・クラッシュから親を守るラッパー。

    子が hard_timeout_sec 以内に結果を返さなければ強制終了して None を返す。
    子が abort（CoinError等）で死んだ場合も検知して None を返す。
    多重プロセスが使えない環境では従来どおりインプロセス実行にフォールバックする。
    戻り値・副作用（last_solve_meta, patterns_evaluated）は solve_mip と同等。
    """
    import multiprocessing as mp
    import queue as _queue
    import time as _time

    try:
        # OS依存：Linux/Macは fork（再インポート不要で高速・堅牢）、
        # Windowsは fork 非対応のため spawn（子で全モジュール再インポート）。
        # いずれも子はDB接続を張り直すため接続継承の問題は回避している。
        methods = mp.get_all_start_methods()
        ctx = mp.get_context("fork" if "fork" in methods else "spawn")
        q = ctx.Queue()
        p = ctx.Process(
            target=_mip_worker,
            args=(type(opt).__module__, type(opt).__name__,
                  opt.plan_date, opt.method, objective_type, q),
            daemon=True,
        )
        p.start()
    except Exception as e:
        # 子プロセスを起動できない環境（一部のWSGI/制限環境など）。
        logger.warning("MIP[%s] 子プロセス起動不可(%s)→インプロセス実行", objective_type, e)
        return solve_mip(opt, objective_type)

    payload = None
    timed_out = False
    deadline = _time.time() + hard_timeout_sec
    while True:
        if _time.time() >= deadline:
            timed_out = True  # 時間切れ（暴走）→こちらから強制終了する
            break
        try:
            payload = q.get(timeout=1.0)
            break
        except _queue.Empty:
            if not p.is_alive():
                break  # 結果を入れずに自滅＝abort（クラッシュ）

    # 後始末：まだ生きていれば強制終了
    if p.is_alive():
        p.terminate()
    p.join(timeout=5)

    if payload is None:
        if timed_out:
            logger.warning(
                "MIP[%s] ハード時間上限%.0fs超過→子プロセス強制終了しフォールバック",
                objective_type, hard_timeout_sec,
            )
            opt.last_solve_meta = {"status": "TIMEOUT_KILLED", "gap": None,
                                   "seconds": hard_timeout_sec}
        else:
            logger.warning(
                "MIP[%s] ソルバーが異常終了(exit=%s)→ヒューリスティックへフォールバック",
                objective_type, p.exitcode,
            )
            opt.last_solve_meta = {"status": "SOLVER_CRASHED", "gap": None, "seconds": 0.0}
        return None

    tag, res, meta, patterns = payload
    opt.last_solve_meta = meta
    try:
        opt.patterns_evaluated += int(patterns)
    except Exception:
        pass
    return res if tag == "ok" else None
