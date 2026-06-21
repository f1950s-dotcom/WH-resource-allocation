import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { getOptimizationAssignments, getOptimizationResults, selectOptimizationResult, getEmployees, getProcesses } from '../api/client';
import GanttChart from '../components/GanttChart';
import type { OptimizationResult } from '../types';

export default function OptimizationDetail() {
  const { resultId } = useParams<{ resultId: string }>();
  const navigate = useNavigate();
  const { data: assignments = [] } = useQuery({ queryKey: ['assignments', resultId], queryFn: () => getOptimizationAssignments(resultId!) });
  const { data: employees = [] } = useQuery({ queryKey: ['employees'], queryFn: getEmployees });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: allResults = [] } = useQuery({ queryKey: ['allResults'], queryFn: () => getOptimizationResults(new Date().toISOString().slice(0,10)) });

  const result: OptimizationResult | undefined = allResults.find((r: OptimizationResult) => r.result_id === resultId);

  const selectMut = useMutation({
    mutationFn: () => selectOptimizationResult(resultId!),
    onSuccess: () => navigate('/shift'),
  });

  const TYPE_LABELS: Record<string, string> = { FASTEST: '案A：最速完了', CHEAPEST: '案B：最低コスト', LEAST_MOVE: '案C：最小移動' };

  return (
    <div className="p-6">
      <div className="flex items-center gap-4 mb-4">
        <button onClick={() => navigate('/optimization')} className="text-blue-600 text-sm hover:underline">← 一覧へ戻る</button>
        <h1 className="text-xl font-bold text-gray-800">配置案詳細 {result ? `(${TYPE_LABELS[result.result_type]})` : ''}</h1>
      </div>

      {result && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-white border rounded p-3"><div className="text-xs text-gray-500">期限遵守</div><div className={`font-semibold mt-1 ${result.is_deadline_met ? 'text-green-600' : 'text-red-600'}`}>{result.is_deadline_met ? '✓ 遵守' : '✗ 違反'}</div></div>
          <div className="bg-white border rounded p-3"><div className="text-xs text-gray-500">総コスト</div><div className="font-semibold mt-1">¥{result.total_cost.toLocaleString()}</div></div>
          <div className="bg-white border rounded p-3"><div className="text-xs text-gray-500">残業コスト</div><div className="font-semibold mt-1 text-orange-600">¥{result.total_overtime_cost.toLocaleString()}</div></div>
          <div className="bg-white border rounded p-3"><div className="text-xs text-gray-500">工程移動回数</div><div className="font-semibold mt-1">{result.total_process_moves}回</div></div>
        </div>
      )}

      <div className="bg-white rounded-lg border p-4 mb-4 overflow-x-auto">
        <h2 className="font-semibold text-gray-700 mb-3">ガントチャート</h2>
        <GanttChart assignments={assignments} employees={employees} processes={processes} />
      </div>

      <button onClick={() => selectMut.mutate()} disabled={selectMut.isPending} className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50">
        {selectMut.isPending ? '確定中...' : 'この案を選択'}
      </button>
    </div>
  );
}
