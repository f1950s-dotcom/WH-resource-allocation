import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDeadlineConditions, updateDeadlineCondition, createDeadlineCondition,
  getSystemConditions, updateSystemCondition, getProcesses,
} from '../../api/client';

export default function Conditions() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'deadlines' | 'system'>('deadlines');
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: deadlines = [] } = useQuery({ queryKey: ['deadlines'], queryFn: getDeadlineConditions });
  const { data: sysConditions = [] } = useQuery({ queryKey: ['sysConditions'], queryFn: getSystemConditions });

  const [deadlineMap, setDeadlineMap] = useState<Record<string, string>>({});
  const [sysMap, setSysMap] = useState<Record<string, string>>({});

  useEffect(() => {
    const m: Record<string, string> = {};
    deadlines.forEach((d: any) => { m[d.process_id] = d.must_finish_by; });
    setDeadlineMap(m);
  }, [deadlines]);

  useEffect(() => {
    const m: Record<string, string> = {};
    sysConditions.forEach((s: any) => { m[s.condition_key] = s.condition_value; });
    setSysMap(m);
  }, [sysConditions]);

  const saveDeadlines = useMutation({
    mutationFn: async () => {
      for (const [process_id, time] of Object.entries(deadlineMap)) {
        const existing = deadlines.find((d: any) => d.process_id === process_id);
        if (existing) await updateDeadlineCondition(existing.deadline_id, { must_finish_by: time, is_active: true });
        else if (time) await createDeadlineCondition({ process_id, must_finish_by: time, is_active: true });
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deadlines'] }),
  });

  const saveSys = useMutation({
    mutationFn: async () => {
      for (const [key, value] of Object.entries(sysMap)) {
        await updateSystemCondition(key, value);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sysConditions'] }),
  });

  // システム条件のうち、汎用テキスト行で編集する項目（表示名マップ）
  const GENERIC_SYS_KEYS: Record<string, string> = {
    overtime_wage_rate: '残業時給倍率',
    overtime_threshold_minutes: '残業開始閾値（分）',
    lunch_break_start: '昼休憩開始時刻',
    lunch_break_end: '昼休憩終了時刻',
    lunch_break_duration_minutes: '昼休憩時間（分）',
    legal_break_threshold_minutes: '法定休憩必要閾値（分）',
    legal_break_minutes: '法定休憩時間（分）',
    time_slot_minutes: '時間粒度（分）',
    overtime_max_end_time: '残業最大終了時刻',
    min_work_minutes: '最低勤務時間（分・0=無効）',
    min_process_assignment_minutes: '1工程の最低配置時間（分・0=無効）',
  };
  // 工程移動ペナルティ専用UIで扱うキー（汎用行からは除外）
  const PENALTY_KEYS = new Set([
    'process_transition_penalty_enabled',
    'process_transition_penalty_rate',
  ]);

  const penaltyEnabled = (sysMap['process_transition_penalty_enabled'] ?? '1') === '1';
  const penaltyRate = parseFloat(sysMap['process_transition_penalty_rate'] ?? '0.30');

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-800 mb-4">条件マスタ</h1>

      <div className="flex border-b mb-5">
        <button onClick={() => setTab('deadlines')} className={`px-4 py-2 text-sm font-medium ${tab === 'deadlines' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>工程完了期限</button>
        <button onClick={() => setTab('system')} className={`px-4 py-2 text-sm font-medium ${tab === 'system' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>システム条件</button>
      </div>

      {tab === 'deadlines' && (
        <>
          <p className="text-sm text-gray-500 mb-4">各ラインの末端工程に完了しなければならない時刻を設定します。</p>
          <div className="bg-white rounded-lg border overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-600">工程名</th>
                  <th className="px-4 py-3 text-left text-gray-600">ライン</th>
                  <th className="px-4 py-3 text-center text-gray-600">完了期限</th>
                </tr>
              </thead>
              <tbody>
                {processes.map((p: any) => (
                  <tr key={p.process_id} className="border-b">
                    <td className="px-4 py-3">{p.process_name}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{p.line_type === 'INBOUND' ? '入庫' : '出庫'}</td>
                    <td className="px-4 py-3 text-center">
                      <input type="time" value={deadlineMap[p.process_id] ?? ''} onChange={e => setDeadlineMap(m => ({ ...m, [p.process_id]: e.target.value }))} className="border rounded px-2 py-1 text-sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button onClick={() => saveDeadlines.mutate()} disabled={saveDeadlines.isPending} className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">保存</button>
        </>
      )}

      {tab === 'system' && (
        <>
          {/* ── 工程移動ペナルティ専用設定 ── */}
          <div className="bg-white rounded-lg border p-5 mb-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h2 className="font-semibold text-gray-800 text-sm">工程移動時の習熟ペナルティ</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  休憩なしで別工程へ移動した直後のスロットは、切り替えコストにより生産性が低下します。
                  このオプションでその影響を最適化に反映させます。
                </p>
              </div>
              {/* オン・オフトグル */}
              <button
                type="button"
                onClick={() => setSysMap(m => ({
                  ...m,
                  process_transition_penalty_enabled: penaltyEnabled ? '0' : '1',
                }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ml-4 ${
                  penaltyEnabled ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  penaltyEnabled ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
            </div>

            {penaltyEnabled && (
              <div className="border-t pt-4">
                <label className="block text-sm text-gray-600 mb-2">
                  生産性低下率
                  <span className="text-xs text-gray-400 ml-2">（移動後の最初のスロットのみ適用）</span>
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={80}
                    step={5}
                    value={Math.round(penaltyRate * 100)}
                    onChange={e => setSysMap(m => ({
                      ...m,
                      process_transition_penalty_rate: (parseInt(e.target.value) / 100).toFixed(2),
                    }))}
                    className="flex-1"
                  />
                  <span className="text-lg font-bold text-blue-600 w-14 text-right">
                    {Math.round(penaltyRate * 100)}%
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>0%（ペナルティなし）</span>
                  <span>80%（ほぼ停止）</span>
                </div>
                <p className="text-xs text-gray-500 mt-2 bg-gray-50 rounded p-2">
                  例）30%低下の場合、熟練度2（基礎生産性100%）で別工程へ移動すると<br />
                  移動後の最初の15分スロットは 100% × 70% = 70% の処理能力になります。
                </p>
              </div>
            )}
          </div>

          {/* ── その他の汎用システム条件 ── */}
          <div className="bg-white rounded-lg border overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-600">条件名</th>
                  <th className="px-4 py-3 text-center text-gray-600">値</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(sysMap)
                  .filter(([key]) => !PENALTY_KEYS.has(key))
                  .map(([key, val]) => (
                    <tr key={key} className="border-b">
                      <td className="px-4 py-3">{GENERIC_SYS_KEYS[key] ?? key}</td>
                      <td className="px-4 py-3 text-center">
                        <input
                          value={val}
                          onChange={e => setSysMap(m => ({ ...m, [key]: e.target.value }))}
                          className="border rounded px-2 py-1 text-sm w-32 text-center"
                        />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          <button onClick={() => saveSys.mutate()} disabled={saveSys.isPending} className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">保存</button>
        </>
      )}
    </div>
  );
}
