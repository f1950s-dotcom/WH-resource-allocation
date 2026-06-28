import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  runOptimization, getOptimizationResults, selectOptimizationResult,
  getOptimizationStatus,
} from '../api/client';

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' }); // JST(YYYY-MM-DD)

const RESULT_LABELS: Record<string, string> = {
  FASTEST: '案A：最速完了',
  CHEAPEST: '案B：最低コスト',
  LEAST_MOVE: '案C：最小移動',
};

const RESULT_DESC: Record<string, string> = {
  FASTEST: '作業を最も早く終わらせる配置',
  CHEAPEST: '期限を守りつつコストを最小化',
  LEAST_MOVE: '期限を守りつつ工程移動を最小化',
};

const ENGINE_LABELS: Record<string, string> = {
  GREEDY: '貪欲＋局所探索（高速）',
  ANNEALING: '焼きなまし法（探索多・中速）',
  ORTOOLS: 'OR-Toolsソルバー（最適志向・低速）',
};
const ENGINE_ORDER = ['GREEDY', 'ANNEALING', 'ORTOOLS'] as const;

// ソルバーの状態を「意味が分かる日本語」に変換する
function statusInfo(r: any): { label: string; color: string; hint: string } {
  const s = r.solver_status;
  if (r.calculation_method === 'GREEDY' || s === 'HEURISTIC') {
    return {
      label: '高速ヒューリスティック',
      color: 'text-gray-600',
      hint: '厳密最適化は行わず、高速な近似手法で解いた結果です',
    };
  }
  if (s === 'OPTIMAL') {
    return {
      label: '最適解を確認 ✓',
      color: 'text-green-600',
      hint: '時間内に「これ以上良い解は存在しない」ことを証明できた厳密最適解です',
    };
  }
  if (s === 'FEASIBLE') {
    return {
      label: '時間内の最良解',
      color: 'text-blue-600',
      hint: '時間切れで打ち切り。実用上は十分ですが、最適である証明はできていません',
    };
  }
  return {
    label: '簡易計算（完了）',
    color: 'text-gray-600',
    hint: 'ソルバーが解を確定できなかったため近似手法で計算しました。作業はすべて完了しています',
  };
}

export default function Optimization() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const date = params.get('date') ?? today();
  const setDate = (d: string) => setParams({ date: d }, { replace: true });
  const [method, setMethod] = useState<'GREEDY' | 'ANNEALING' | 'ORTOOLS'>('GREEDY');
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: results = [], refetch } = useQuery({
    queryKey: ['optResults', date],
    queryFn: () => getOptimizationResults(date),
  });

  const runMut = useMutation({
    mutationFn: () => runOptimization(date, method),
    onSuccess: () => { setPolling(true); },
  });

  const selectMut = useMutation({
    mutationFn: (resultId: string) => selectOptimizationResult(resultId, date),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['optResults', date] }); navigate(`/shift?date=${date}`); },
  });

  // 計算完了はサーバーの実行状態(running)で判定する。
  // エンジン別に結果が蓄積されるため、件数では新しい計算の完了を判定できない。
  useEffect(() => {
    if (polling) {
      pollRef.current = setInterval(async () => {
        try {
          const st = await getOptimizationStatus(date);
          if (!st.running) {
            await refetch();
            setPolling(false);
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          // ネットワーク一時失敗は次回ポーリングで回復
        }
      }, 1500);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [polling]);

  // エンジン別にグルーピング（実際に結果のあるエンジンのみ表示）
  const enginesWithResults = ENGINE_ORDER.filter(
    eng => (results as any[]).some(r => (r.calculation_method ?? 'GREEDY') === eng)
  );

  // この日に勤務条件のある従業員が1人もいない（土日など）と、結果は出るが
  // 全員未配置になる。原因が分かるようバナーで明示する。
  const noStaffDay = (results as any[]).length > 0
    && (results as any[]).every(r => (r.available_headcount ?? 0) === 0);

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-1">人員配置最適化提案</h1>
      <p className="text-xs text-gray-400 mb-4">
        計算エンジンを変えて実行すると、結果はエンジンごとに残り、下に並べて比較できます。
      </p>
      <div className="flex gap-4 items-end mb-6">
        <div>
          <label className="block text-xs text-gray-500 mb-1">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">計算エンジン</label>
          <select value={method} onChange={e => setMethod(e.target.value as any)} className="border rounded px-3 py-1.5 text-sm" disabled={polling}>
            <option value="GREEDY">貪欲＋局所探索（高速）</option>
            <option value="ANNEALING">焼きなまし法（探索多・中速）</option>
            <option value="ORTOOLS">OR-Toolsソルバー（最適志向・低速）</option>
          </select>
        </div>
        <button
          onClick={() => { runMut.mutate(); }}
          disabled={runMut.isPending || polling}
          className="bg-blue-600 text-white px-5 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {polling ? '計算中...' : (runMut.isPending ? '送信中...' : '最適化実行')}
        </button>
        {polling && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            {ENGINE_LABELS[method]} で計算中...
          </div>
        )}
      </div>

      {noStaffDay && (
        <div className="mb-5 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          <b>この日は配置できる従業員がいません。</b>
          選択した日付（曜日）に<b>勤務条件が登録された従業員が1人もいない</b>ため、誰も配置されません。
          土曜・日曜などを稼働させる場合は、<b>従業員マスタ ＞ 勤務条件</b>でその曜日の勤務を登録してください。
        </div>
      )}

      {enginesWithResults.length > 0 ? (
        <div className="space-y-8">
          {enginesWithResults.map(engine => {
            const engineResults = (results as any[]).filter(
              r => (r.calculation_method ?? 'GREEDY') === engine
            );
            return (
              <section key={engine}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="inline-block px-2 py-0.5 rounded bg-gray-700 text-white text-xs font-medium">
                    エンジン
                  </span>
                  <h2 className="font-bold text-gray-800">{ENGINE_LABELS[engine]}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {(['FASTEST', 'CHEAPEST'] as const).map(type => {
                    const r = engineResults.find((x: any) => x.result_type === type);
                    if (!r) return (
                      <div key={type} className="bg-white rounded-lg border p-5 text-center text-gray-300 text-sm flex items-center justify-center">
                        （{RESULT_LABELS[type]} の結果なし）
                      </div>
                    );
                    const si = statusInfo(r);
                    return (
                      <div key={type} className={`bg-white rounded-lg border-2 p-5 ${r.is_selected ? 'border-green-500' : 'border-gray-200'}`}>
                        <h3 className="font-bold text-gray-800 mb-1">{RESULT_LABELS[type]}</h3>
                        <p className="text-xs text-gray-400 mb-4">{RESULT_DESC[type]}</p>
                        <div className="space-y-2 mb-4">
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-500">期限遵守</span>
                            <span className={r.is_deadline_met ? 'text-green-600 font-medium' : 'text-red-500 font-medium'}>
                              {r.is_deadline_met ? '✓ 遵守' : '✗ 定時超過'}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm" title="当日処理しきれず残った作業量（全工程の未処理量合計）">
                            <span className="text-gray-500">作業残</span>
                            <span className={r.total_unprocessed != null && r.total_unprocessed > 0.5 ? 'text-red-500 font-medium' : 'text-green-600 font-medium'}>
                              {r.total_unprocessed == null ? '—'
                                : r.total_unprocessed > 0.5 ? `あり（${Math.round(r.total_unprocessed).toLocaleString()} 個）`
                                : 'なし'}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-500">総人件費</span>
                            <span className="font-semibold">¥{r.total_cost.toLocaleString()}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-500">うち残業費</span>
                            <span className={r.total_overtime_cost > 0 ? 'text-orange-500' : 'text-gray-600'}>
                              ¥{r.total_overtime_cost.toLocaleString()}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-500">作業完了時間</span>
                            <span className="font-medium">{r.completion_time ?? '—'}</span>
                          </div>
                          <div className="flex justify-between text-sm" title="当日出社しうる人数のうち、実際に配置された人数">
                            <span className="text-gray-500">出社人数</span>
                            <span className="font-medium">
                              {r.assigned_headcount ?? '—'}
                              {r.available_headcount != null && (
                                <span className="text-gray-400"> / {r.available_headcount} 名</span>
                              )}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm" title="実働スロットの合計（昼休み等の休憩は除く）">
                            <span className="text-gray-500">総人時（昼休み除く）</span>
                            <span className="font-medium">
                              {r.total_work_hours != null ? `${r.total_work_hours.toLocaleString()} 人時` : '—'}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-500">工程移動回数</span>
                            <span>
                              {r.total_process_moves} 回
                              {r.process_moves_before_repair != null
                                && r.process_moves_before_repair > r.total_process_moves && (
                                <span className="text-xs text-green-600 ml-1">
                                  （連続化前 {r.process_moves_before_repair} 回）
                                </span>
                              )}
                            </span>
                          </div>
                        </div>

                        {/* 計算ログ：このカードがどう計算されたかを分かりやすく表示 */}
                        <div className="bg-gray-50 rounded p-3 mb-4 space-y-1.5">
                          <div className="text-xs font-medium text-gray-500 mb-1">計算ログ</div>
                          <div className="flex justify-between text-xs" title={si.hint}>
                            <span className="text-gray-500">計算状態</span>
                            <span className={`font-medium ${si.color}`}>{si.label}</span>
                          </div>
                          <div className="flex justify-between text-xs" title="最良解と理論限界(下界)の差。0%＝最適を証明済み。小さいほど最適に近い">
                            <span className="text-gray-500">最適性ギャップ</span>
                            <span className="text-gray-700">
                              {r.solver_gap != null ? `${(r.solver_gap * 100).toFixed(1)}%` : '—'}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs" title="ソルバーが求解に要した実時間">
                            <span className="text-gray-500">計算時間</span>
                            <span className="text-gray-700">
                              {r.solve_seconds != null ? `${r.solve_seconds.toFixed(2)} 秒` : '—'}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs" title="探索した配置パターン数の目安">
                            <span className="text-gray-500">検証パターン数</span>
                            <span className="text-gray-700">{(r.patterns_evaluated ?? 0).toLocaleString()} 通り</span>
                          </div>
                          {r.process_moves_before_repair != null && (
                            <div className="flex justify-between text-xs" title="細切れの工程切替を、処理量・コストを変えずに減らす後処理">
                              <span className="text-gray-500">連続化リペア</span>
                              <span className="text-gray-700">
                                工程切替 {r.process_moves_before_repair} → {r.total_process_moves} 回
                                {r.process_moves_before_repair > r.total_process_moves
                                  ? `（${r.process_moves_before_repair - r.total_process_moves} 回削減）`
                                  : '（削減なし）'}
                              </span>
                            </div>
                          )}
                        </div>

                        <div className="flex gap-2">
                          <button onClick={() => navigate(`/optimization/${r.result_id}?date=${date}`)} className="flex-1 border border-gray-300 text-gray-600 text-xs py-2 rounded hover:bg-gray-50">
                            詳細を見る
                          </button>
                          <button
                            onClick={() => selectMut.mutate(r.result_id)}
                            disabled={selectMut.isPending}
                            className={`flex-1 text-xs py-2 rounded ${r.is_selected ? 'bg-green-600 text-white' : 'bg-blue-600 text-white hover:bg-blue-700'}`}
                          >
                            {r.is_selected ? '✓ 選択済み' : 'この案を選択'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          <p className="mb-3">最適化結果がありません</p>
          <p className="text-sm">「最適化実行」を押して3案を生成してください</p>
        </div>
      )}
    </div>
  );
}
