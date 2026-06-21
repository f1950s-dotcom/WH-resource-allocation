import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getProcesses, getVolumeRules, createVolumeRule, updateVolumeRule } from '../../api/client';

export default function VolumeRules() {
  const qc = useQueryClient();
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: rules = [] } = useQuery({ queryKey: ['volumeRules'], queryFn: getVolumeRules });
  const [tab, setTab] = useState<'INBOUND' | 'OUTBOUND'>('INBOUND');
  const [rateMap, setRateMap] = useState<Record<string, string>>({});

  useEffect(() => {
    const m: Record<string, string> = {};
    rules.forEach((r: any) => { m[`${r.source_type}__${r.process_id}`] = String(r.conversion_rate); });
    setRateMap(m);
  }, [rules]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const filtered = processes.filter((p: any) => p.line_type === tab);
      for (const p of filtered) {
        const key = `${tab}__${p.process_id}`;
        const rate = parseFloat(rateMap[key] ?? '0');
        if (isNaN(rate)) continue;
        const existing = rules.find((r: any) => r.source_type === tab && r.process_id === p.process_id);
        if (existing) {
          await updateVolumeRule(existing.rule_id, { conversion_rate: rate });
        } else if (rate > 0) {
          await createVolumeRule({ source_type: tab, process_id: p.process_id, conversion_rate: rate });
        }
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['volumeRules'] }),
  });

  const filtered = processes.filter((p: any) => p.line_type === tab);

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-800 mb-4">物量変換マスタ</h1>
      <p className="text-sm text-gray-500 mb-5">入出庫量 × 変換係数 = 各工程の処理量</p>

      <div className="flex border-b mb-5">
        {(['INBOUND', 'OUTBOUND'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium ${tab === t ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>
            {t === 'INBOUND' ? '入庫ライン' : '出庫ライン'}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-lg border overflow-hidden mb-4">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-gray-600">工程名</th>
              <th className="px-4 py-3 text-center text-gray-600">変換係数</th>
              <th className="px-4 py-3 text-left text-gray-600 text-xs">例）{tab === 'INBOUND' ? '入庫' : '出庫'}量 × 係数 = 処理量</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p: any) => {
              const key = `${tab}__${p.process_id}`;
              return (
                <tr key={p.process_id} className="border-b">
                  <td className="px-4 py-3">{p.process_name}</td>
                  <td className="px-4 py-3 text-center">
                    <input
                      type="number"
                      step="0.01"
                      value={rateMap[key] ?? ''}
                      onChange={e => setRateMap(m => ({ ...m, [key]: e.target.value }))}
                      className="border rounded px-2 py-1 text-sm w-24 text-center"
                      placeholder="0.00"
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {rateMap[key] ? `例: 100個 × ${rateMap[key]} = ${(100 * parseFloat(rateMap[key] || '0')).toFixed(0)}個` : '─'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="p-6 text-center text-gray-400 text-sm">工程がありません。先に工程マスタを登録してください。</div>}
      </div>

      <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending} className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
        {saveMut.isPending ? '保存中...' : '保存'}
      </button>
    </div>
  );
}
