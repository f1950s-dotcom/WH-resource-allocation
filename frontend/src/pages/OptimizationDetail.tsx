import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getOptimizationAssignments, selectOptimizationResult, getOptimizationResults, getProcesses } from '../api/client';

const PROCESS_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-purple-500',
  'bg-pink-500', 'bg-indigo-500', 'bg-red-500', 'bg-teal-500',
];

const today = () => new Date().toISOString().slice(0, 10);

export default function OptimizationDetail() {
  const { resultId } = useParams<{ resultId: string }>();
  const [params] = useSearchParams();
  const date = params.get('date') ?? today();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: assignments = [] } = useQuery({ queryKey: ['assignments', resultId, date], queryFn: () => getOptimizationAssignments(resultId!, date) });
  const { data: results = [] } = useQuery({ queryKey: ['optResults', date], queryFn: () => getOptimizationResults(date) });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });

  const result = results.find((r: any) => r.result_id === resultId);
  const procList = [...new Set(assignments.map((a: any) => a.process_id as string).filter(Boolean))] as string[];
  const procColorMap = Object.fromEntries(procList.map((pid, i) => [pid, PROCESS_COLORS[i % PROCESS_COLORS.length]]));
  const procMap = Object.fromEntries(processes.map((p: any) => [p.process_id, p]));

  const employeeIds = [...new Set(assignments.map((a: any) => a.employee_id as string))] as string[];
  const slots: string[] = ([...new Set(assignments.map((a: any) => a.time_slot_start as string))] as string[]).sort();

  const getAssignment = (empId: string, slot: string) =>
    assignments.find((a: any) => a.employee_id === empId && a.time_slot_start === slot);

  const selectMut = useMutation({
    mutationFn: () => selectOptimizationResult(resultId!, date),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['optResults', date] }); navigate(`/shift?date=${date}`); },
  });

  const RESULT_LABELS: Record<string, string> = { FASTEST: '案A：最速完了', CHEAPEST: '案B：最低コスト', LEAST_MOVE: '案C：最小移動' };

  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => navigate(-1)} className="text-gray-500 hover:text-gray-700 text-sm">← 戻る</button>
        <h1 className="text-xl font-bold text-gray-800">
          配置詳細：{result ? RESULT_LABELS[result.result_type] : ''}
        </h1>
      </div>

      {result && (
        <div className="bg-white rounded-lg border p-4 mb-5 grid grid-cols-4 gap-4 text-sm">
          <div><span className="text-gray-500">期限遵守</span><p className={`font-semibold ${result.is_deadline_met ? 'text-green-600' : 'text-red-500'}`}>{result.is_deadline_met ? '✓ 遵守' : '✗ 超過'}</p></div>
          <div><span className="text-gray-500">総人件費</span><p className="font-semibold">¥{result.total_cost.toLocaleString()}</p></div>
          <div><span className="text-gray-500">うち残業費</span><p className="font-semibold text-orange-500">¥{result.total_overtime_cost.toLocaleString()}</p></div>
          <div><span className="text-gray-500">工程移動回数</span><p className="font-semibold">{result.total_process_moves} 回</p></div>
        </div>
      )}

      <div className="flex gap-3 flex-wrap mb-4">
        {procList.map(pid => (
          <div key={pid} className="flex items-center gap-1 text-xs">
            <div className={`w-3 h-3 rounded ${procColorMap[pid]}`} />
            <span>{procMap[pid]?.process_name ?? pid}</span>
          </div>
        ))}
        <div className="flex items-center gap-1 text-xs"><div className="w-3 h-3 rounded bg-gray-200" /><span>昼休憩</span></div>
        <div className="flex items-center gap-1 text-xs"><div className="w-3 h-3 rounded bg-gray-300" /><span>法定休憩</span></div>
      </div>

      <div className="bg-white rounded-lg border overflow-auto" style={{ maxHeight: '65vh' }}>
        <table className="text-xs border-collapse">
          <thead className="sticky top-0 bg-white z-10">
            <tr>
              <th className="border px-3 py-2 bg-gray-50 text-left min-w-28 sticky left-0 z-20">人員名</th>
              {slots.map(slot => (
                <th key={slot} className="border px-1 py-2 bg-gray-50 text-center min-w-14">{slot}</th>
              ))}
              <th className="border px-3 py-2 bg-gray-50 text-right">費用</th>
            </tr>
          </thead>
          <tbody>
            {employeeIds.map(empId => {
              const empAssignments = assignments.filter((a: any) => a.employee_id === empId);
              const totalCost = empAssignments.reduce((s: number, a: any) => s + a.slot_cost, 0);
              const empName = empAssignments[0]?.employee_name ?? empId;
              return (
                <tr key={empId} className="border-b hover:bg-gray-50">
                  <td className="border px-3 py-1.5 font-medium sticky left-0 bg-white z-10">{empName}</td>
                  {slots.map(slot => {
                    const a = getAssignment(empId, slot);
                    if (!a) return <td key={slot} className="border px-1 py-1.5" />;
                    const bgClass =
                      a.slot_type === 'LUNCH_BREAK' ? 'bg-gray-200' :
                      a.slot_type === 'LEGAL_BREAK' ? 'bg-gray-300' :
                      a.slot_type === 'OFF' ? '' :
                      (procColorMap[a.process_id] ?? 'bg-gray-400');
                    return (
                      <td key={slot} className={`border px-1 py-1.5 text-center ${bgClass} ${a.is_overtime ? 'ring-2 ring-orange-400 ring-inset' : ''}`}>
                        <span className={a.slot_type === 'WORK' ? 'text-white text-xs' : 'text-gray-600 text-xs'}>
                          {a.slot_type === 'WORK' ? (procMap[a.process_id]?.process_name?.slice(0, 2) ?? '') :
                           a.slot_type === 'LUNCH_BREAK' ? '昼' :
                           a.slot_type === 'LEGAL_BREAK' ? '休' : ''}
                        </span>
                      </td>
                    );
                  })}
                  <td className="border px-3 py-1.5 text-right font-medium">¥{totalCost.toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex gap-3">
        <button onClick={() => navigate(-1)} className="px-4 py-2 border rounded text-sm text-gray-600 hover:bg-gray-50">戻る</button>
        <button onClick={() => selectMut.mutate()} disabled={selectMut.isPending} className="px-6 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {selectMut.isPending ? '処理中...' : 'この案を選択してシフト生成へ'}
        </button>
      </div>
    </div>
  );
}
