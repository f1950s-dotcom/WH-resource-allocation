import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getVolumeExpansions, runVolumeExpansion, getProcesses } from '../api/client';

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' }); // JST(YYYY-MM-DD)

const HEAT_COLORS = [
  'bg-white',
  'bg-blue-100',
  'bg-blue-200',
  'bg-blue-400',
  'bg-blue-600',
  'bg-blue-800',
];

function heatColor(val: number): string {
  if (val <= 0) return HEAT_COLORS[0];
  if (val < 50) return HEAT_COLORS[1];
  if (val < 200) return HEAT_COLORS[2];
  if (val < 500) return HEAT_COLORS[3];
  if (val < 1000) return HEAT_COLORS[4];
  return HEAT_COLORS[5];
}

export default function VolumeExpansion() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [date, setDate] = useState(params.get('date') ?? today());

  const { data: expansions = [] } = useQuery({ queryKey: ['expansions', date], queryFn: () => getVolumeExpansions(date) });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });

  const expandMut = useMutation({
    mutationFn: () => runVolumeExpansion(date),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expansions', date] }),
  });

  const slots = [...new Set<string>(expansions.map((e: any) => e.time_slot_start))].sort();
  const procIds = [...new Set<string>(expansions.map((e: any) => e.process_id))];
  const procMap = Object.fromEntries(processes.map((p: any) => [p.process_id, p]));

  const getValue = (procId: string, slot: string) => {
    const e = expansions.find((x: any) => x.process_id === procId && x.time_slot_start === slot);
    return e?.process_volume ?? 0;
  };

  const procTotal = (procId: string) => expansions.filter((e: any) => e.process_id === procId).reduce((s: number, e: any) => s + e.process_volume, 0);

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-4">物量展開</h1>
      <div className="flex gap-4 items-end mb-5">
        <div>
          <label className="block text-xs text-gray-500 mb-1">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        </div>
        <button onClick={() => expandMut.mutate()} disabled={expandMut.isPending} className="bg-blue-600 text-white px-5 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {expandMut.isPending ? '計算中...' : '展開実行'}
        </button>
        {expandMut.isSuccess && <span className="text-green-600 text-sm">✓ 展開完了</span>}
        {expandMut.isError && <span className="text-red-600 text-sm">エラーが発生しました</span>}
      </div>

      {expansions.length > 0 ? (
        <>
          <div className="bg-white rounded-lg border overflow-auto mb-4" style={{ maxHeight: '60vh' }}>
            <table className="text-xs border-collapse">
              <thead className="sticky top-0 bg-white z-10">
                <tr>
                  <th className="border px-3 py-2 bg-gray-50 text-left min-w-20">時間帯</th>
                  {procIds.map(pid => (
                    <th key={pid} className="border px-2 py-2 bg-gray-50 text-center min-w-24">
                      {procMap[pid]?.process_name ?? pid}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {slots.map(slot => (
                  <tr key={slot}>
                    <td className="border px-3 py-1.5 text-gray-600">{slot}</td>
                    {procIds.map(pid => {
                      const val = getValue(pid, slot);
                      return (
                        <td key={pid} className={`border px-2 py-1.5 text-center ${heatColor(val)}`}>
                          {val > 0 ? <span className={val >= 500 ? 'text-white' : 'text-gray-800'}>{val.toLocaleString()}</span> : ''}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr className="font-semibold bg-gray-50">
                  <td className="border px-3 py-2">合計(作業量)</td>
                  {procIds.map(pid => (
                    <td key={pid} className="border px-2 py-2 text-center">{procTotal(pid).toLocaleString()}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
            <span>作業量（凡例）：</span>
            {['0', '〜50', '〜200', '〜500', '〜1000', '1000超'].map((lbl, i) => (
              <div key={lbl} className="flex items-center gap-1">
                <div className={`w-4 h-4 rounded ${HEAT_COLORS[i]} border`} />
                <span>{lbl}</span>
              </div>
            ))}
          </div>

          <button onClick={() => navigate(`/optimization?date=${date}`)} className="bg-green-600 text-white px-6 py-2 rounded text-sm hover:bg-green-700">
            最適化提案へ進む →
          </button>
        </>
      ) : (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          <p className="mb-3">展開結果がありません</p>
          <p className="text-sm">物量登録後に「展開実行」を押してください</p>
        </div>
      )}
    </div>
  );
}
