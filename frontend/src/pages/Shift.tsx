import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { getShifts, generateShifts, exportShifts, getEmployees, getProcesses, getOptimizationResults } from '../api/client';
import { useNavigate } from 'react-router-dom';
import TimeSlotGrid from '../components/TimeSlotGrid';
import type { OptimizationResult } from '../types';

export default function Shift() {
  const navigate = useNavigate();
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [viewMode, setViewMode] = useState<'employee' | 'process'>('employee');

  const { data: shifts = [], refetch } = useQuery({ queryKey: ['shifts', date], queryFn: () => getShifts(date) });
  const { data: employees = [] } = useQuery({ queryKey: ['employees'], queryFn: getEmployees });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: results = [] } = useQuery({ queryKey: ['results', date], queryFn: () => getOptimizationResults(date) });

  const selected: OptimizationResult | undefined = results.find((r: OptimizationResult) => r.is_selected);

  const genMut = useMutation({
    mutationFn: () => generateShifts(date),
    onSuccess: () => refetch(),
  });

  const exportMut = useMutation({
    mutationFn: async () => {
      const blob = await exportShifts(date);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `shift_${date}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    },
  });

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-4">シフト生成</h1>
      <div className="flex flex-wrap gap-4 items-center mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        </div>
        <button onClick={() => genMut.mutate()} disabled={genMut.isPending} className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50">
          {genMut.isPending ? '生成中...' : 'シフト生成'}
        </button>
        <button onClick={() => exportMut.mutate()} disabled={exportMut.isPending} className="border border-gray-400 text-gray-600 px-4 py-2 rounded text-sm hover:bg-gray-50 disabled:opacity-50">
          Excelダウンロード
        </button>
        <button onClick={() => navigate('/optimization')} className="text-blue-600 text-sm hover:underline">← 再最適化へ戻る</button>
      </div>

      {selected && (
        <div className="bg-blue-50 border border-blue-200 rounded p-4 mb-4 text-sm">
          <div className="font-semibold text-blue-800 mb-1">選択済み案</div>
          <div className="grid grid-cols-3 gap-4 text-gray-700">
            <span>総コスト: ¥{selected.total_cost.toLocaleString()}</span>
            <span>残業: ¥{selected.total_overtime_cost.toLocaleString()}</span>
            <span>移動: {selected.total_process_moves}回</span>
          </div>
        </div>
      )}

      {shifts.length > 0 && (
        <>
          <div className="flex gap-2 mb-4">
            {[{ id: 'employee', label: '人別シフト' }, { id: 'process', label: '工程別シフト' }].map(v => (
              <button key={v.id} onClick={() => setViewMode(v.id as typeof viewMode)} className={`px-4 py-2 text-sm rounded ${viewMode === v.id ? 'bg-blue-600 text-white' : 'bg-white border text-gray-600 hover:bg-gray-50'}`}>{v.label}</button>
            ))}
          </div>
          <div className="bg-white rounded-lg border p-4 overflow-x-auto">
            <TimeSlotGrid assignments={shifts} employees={employees} processes={processes} viewMode={viewMode} />
          </div>
        </>
      )}
      {shifts.length === 0 && !genMut.isPending && (
        <div className="text-gray-400 text-sm">シフト生成ボタンを押してください</div>
      )}
    </div>
  );
}
