import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { runOptimization, getOptimizationResults, selectOptimizationResult } from '../api/client';

const today = () => new Date().toISOString().slice(0, 10);

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

export default function Optimization() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [date, setDate] = useState(params.get('date') ?? today());
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: results = [], refetch } = useQuery({
    queryKey: ['optResults', date],
    queryFn: () => getOptimizationResults(date),
  });

  const runMut = useMutation({
    mutationFn: () => runOptimization(date),
    onSuccess: () => { setPolling(true); },
  });

  const selectMut = useMutation({
    mutationFn: (resultId: string) => selectOptimizationResult(resultId, date),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['optResults', date] }); navigate(`/shift?date=${date}`); },
  });

  useEffect(() => {
    if (polling) {
      pollRef.current = setInterval(async () => {
        const res = await refetch();
        if (res.data && res.data.length >= 3) {
          setPolling(false);
          if (pollRef.current) clearInterval(pollRef.current);
        }
      }, 2000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [polling]);

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-4">人員配置最適化提案</h1>
      <div className="flex gap-4 items-end mb-6">
        <div>
          <label className="block text-xs text-gray-500 mb-1">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
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
            3案を計算しています...
          </div>
        )}
      </div>

      {results.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {(['FASTEST', 'CHEAPEST', 'LEAST_MOVE'] as const).map(type => {
            const r = results.find((x: any) => x.result_type === type);
            if (!r) return (
              <div key={type} className="bg-white rounded-lg border p-5 animate-pulse">
                <div className="h-4 bg-gray-200 rounded mb-3" />
                <div className="h-3 bg-gray-100 rounded mb-2" />
                <div className="h-3 bg-gray-100 rounded" />
              </div>
            );
            return (
              <div key={type} className={`bg-white rounded-lg border-2 p-5 ${r.is_selected ? 'border-green-500' : 'border-gray-200'}`}>
                <h3 className="font-bold text-gray-800 mb-1">{RESULT_LABELS[type]}</h3>
                <p className="text-xs text-gray-400 mb-4">{RESULT_DESC[type]}</p>
                <div className="space-y-2 mb-4">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">期限遵守</span>
                    <span className={r.is_deadline_met ? 'text-green-600 font-medium' : 'text-red-500 font-medium'}>
                      {r.is_deadline_met ? '✓ 遵守' : '✗ 超過'}
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
                    <span className="text-gray-500">工程移動回数</span>
                    <span>{r.total_process_moves} 回</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">検証パターン数</span>
                    <span>{(r.patterns_evaluated ?? 0).toLocaleString()} 通り</span>
                  </div>
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
      ) : (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          <p className="mb-3">最適化結果がありません</p>
          <p className="text-sm">「最適化実行」を押して3案を生成してください</p>
        </div>
      )}
    </div>
  );
}
