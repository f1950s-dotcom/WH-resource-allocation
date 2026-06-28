import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getVolumePlans, saveVolumePlans } from '../api/client';

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' }); // JST(YYYY-MM-DD)

function generateSlots(): string[] {
  const slots: string[] = [];
  for (let h = 6; h < 22; h++) {
    for (const m of [0, 15, 30, 45]) {
      slots.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
    }
  }
  return slots;
}

const SLOTS = generateSlots();

export default function VolumePlan() {
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const [date, setDate] = useState(params.get('date') ?? today());
  const [tab, setTab] = useState<'INBOUND' | 'OUTBOUND'>('INBOUND');
  const [volumeMap, setVolumeMap] = useState<Record<string, string>>({});

  const { data: plans = [] } = useQuery({ queryKey: ['volumePlans', date], queryFn: () => getVolumePlans(date) });

  useEffect(() => {
    const m: Record<string, string> = {};
    plans.forEach((p: any) => { m[`${p.volume_type}__${p.time_slot_start}`] = String(p.volume); });
    setVolumeMap(m);
  }, [plans]);

  const saveMut = useMutation({
    mutationFn: () => {
      // 入庫・出庫の両方を一度に保存する。タブ切替で入力した内容が
      // 保存対象から漏れないよう、volumeMap に入っている両タイプを送る。
      const planList = (['INBOUND', 'OUTBOUND'] as const).flatMap(type =>
        SLOTS.map(slot => ({
          volume_type: type,
          time_slot_start: slot,
          volume: parseFloat(volumeMap[`${type}__${slot}`] ?? '0') || 0,
        }))
      );
      return saveVolumePlans(date, planList);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['volumePlans', date] }),
  });

  const handleCsv = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const lines = (ev.target?.result as string).split('\n').slice(1);
      const m = { ...volumeMap };
      lines.forEach(line => {
        const [slot, vol] = line.split(',');
        if (slot && vol) m[`${tab}__${slot.trim()}`] = vol.trim();
      });
      setVolumeMap(m);
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const total = SLOTS.reduce((sum, s) => sum + (parseFloat(volumeMap[`${tab}__${s}`] ?? '0') || 0), 0);

  const hourTotal = (hour: number) => {
    return [0, 15, 30, 45].reduce((sum, m) => {
      const slot = `${String(hour).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      return sum + (parseFloat(volumeMap[`${tab}__${slot}`] ?? '0') || 0);
    }, 0);
  };

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-4">物量登録</h1>
      <div className="flex gap-4 items-center mb-5">
        <div>
          <label className="block text-xs text-gray-500 mb-1">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        </div>
        <div className="flex border-b self-end">
          {(['INBOUND', 'OUTBOUND'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium ${tab === t ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>
              {t === 'INBOUND' ? '入庫' : '出庫'}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border overflow-hidden mb-4">
        <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b">
          <span className="text-sm font-medium text-gray-700">合計: <span className="text-blue-600 font-bold">{total.toLocaleString()} 個</span></span>
          <label className="cursor-pointer text-sm text-blue-600 hover:underline">
            CSVインポート
            <input type="file" accept=".csv" onChange={handleCsv} className="hidden" />
          </label>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0 border-b">
              <tr>
                <th className="px-4 py-2 text-left text-gray-600 w-28">時間帯</th>
                <th className="px-4 py-2 text-right text-gray-600">物量（個）</th>
                <th className="px-4 py-2 text-right text-gray-600 w-32">時間合計</th>
              </tr>
            </thead>
            <tbody>
              {SLOTS.map((slot) => {
                const [h, m] = slot.split(':').map(Number);
                const isHourEnd = m === 45;
                const key = `${tab}__${slot}`;
                return (
                  <tr key={slot} className={`border-b ${isHourEnd ? 'border-b-2 border-gray-300' : ''}`}>
                    <td className="px-4 py-1.5 text-gray-600">{slot}</td>
                    <td className="px-4 py-1.5">
                      <input
                        type="number"
                        min="0"
                        inputMode="decimal"
                        value={volumeMap[key] ?? ''}
                        onChange={e => setVolumeMap(prev => ({ ...prev, [key]: e.target.value }))}
                        className="w-full text-right border rounded px-2 py-1 text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        placeholder="0"
                      />
                    </td>
                    <td className="px-4 py-1.5 text-right text-gray-500">
                      {isHourEnd && <span>{hourTotal(h).toLocaleString()}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex gap-3">
        <button onClick={() => setVolumeMap(m => { const n = { ...m }; SLOTS.forEach(s => delete n[`${tab}__${s}`]); return n; })} className="px-4 py-2 border rounded text-sm text-gray-600 hover:bg-gray-50">クリア</button>
        <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending} className="px-6 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {saveMut.isPending ? '保存中...' : '保存'}
        </button>
        <span className="self-center text-xs text-gray-400">保存ボタンで入庫・出庫の両方をまとめて保存します</span>
        {saveMut.isSuccess && <span className="self-center text-green-600 text-sm">✓ 入庫・出庫を保存しました</span>}
      </div>
    </div>
  );
}
