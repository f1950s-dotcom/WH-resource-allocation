import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getShifts, exportShifts, getProcesses, getShiftFlow } from '../api/client';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const today = () => new Date().toISOString().slice(0, 10);

const PROCESS_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-purple-500',
  'bg-pink-500', 'bg-indigo-500', 'bg-red-500', 'bg-teal-500',
];
const CHART_COLORS = ['#3b82f6', '#22c55e', '#eab308', '#a855f7', '#ec4899', '#6366f1', '#ef4444', '#14b8a6'];

function BufferChart({ slots, pids, simCumData, procMap, chartColors }: {
  slots: string[];
  pids: string[];
  simCumData: Record<string, Array<{ slot: string; 処理残: number; [k: string]: any }>>;
  procMap: Record<string, any>;
  chartColors: string[];
}) {
  const bufferData = slots.map(slot => {
    const row: Record<string, any> = { slot };
    pids.forEach(pid => {
      const name = procMap[pid]?.process_name ?? pid;
      const point = simCumData[pid]?.find(d => d.slot === slot);
      row[`${name}_滞留`] = point?.処理残 ?? null;
    });
    return row;
  });
  const hasBufferMax = pids.some(pid => (procMap[pid]?.buffer_capacity ?? 0) > 0);
  return (
    <div className="mt-6">
      <h4 className="font-semibold text-gray-700 mb-1 text-sm">工程間滞留量（バッファ）</h4>
      <div className="mb-2 text-xs text-gray-400 flex gap-4">
        <span>実線：実際に工程間に滞留している数（処理残）</span>
        {hasBufferMax && <span>点線：バッファ上限 Max値</span>}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={bufferData} margin={{ top: 5, right: 80, left: 10, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="slot" angle={-60} textAnchor="end" tick={{ fontSize: 10 }} interval={1} />
          <YAxis label={{ value: '滞留量', angle: -90, position: 'insideLeft', fontSize: 11 }} allowDecimals={false} />
          <Tooltip formatter={(value: any) => [`${Number(value).toLocaleString()}`]} />
          <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
          {pids.map((pid, i) => {
            const name = procMap[pid]?.process_name ?? pid;
            const color = chartColors[i % chartColors.length];
            const bufMax = procMap[pid]?.buffer_capacity ?? 0;
            return [
              <Line key={`${pid}_滞留`} type="monotone" dataKey={`${name}_滞留`} stroke={color} strokeWidth={2} dot={false} name={`${name} 滞留`} connectNulls />,
              bufMax > 0 ? (
                <ReferenceLine
                  key={`${pid}_max`}
                  y={bufMax}
                  stroke={color}
                  strokeDasharray="3 4"
                  ifOverflow="extendDomain"
                  label={{ value: `${name} Max ${bufMax}`, position: 'right', fontSize: 9, fill: color }}
                />
              ) : null,
            ];
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Shift() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [date, setDate] = useState(params.get('date') ?? today());
  const [tab, setTab] = useState<'employee' | 'process' | 'graph'>('employee');
  const [downloading, setDownloading] = useState(false);

  const { data: shifts } = useQuery({ queryKey: ['shifts', date], queryFn: () => getShifts(date) });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: shiftFlow } = useQuery({ queryKey: ['shiftFlow', date], queryFn: () => getShiftFlow(date) });

  const procMap = Object.fromEntries(processes.map((p: any) => [p.process_id, p]));
  const procList = processes.map((p: any) => p.process_id);
  const procColorMap = Object.fromEntries(procList.map((pid: string, i: number) => [pid, PROCESS_COLORS[i % PROCESS_COLORS.length]]));

  const handleExport = async () => {
    setDownloading(true);
    try {
      const blob = await exportShifts(date);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `shift_${date}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  const employeeRows: any[] = shifts?.employees ?? [];

  const allSlots = [...new Set(
    employeeRows.flatMap((e: any) => e.slots.map((s: any) => s.time_slot_start))
  )].sort() as string[];

  const processSlotMap: Record<string, Record<string, string[]>> = {};
  procList.forEach((pid: string) => { processSlotMap[pid] = {}; });
  employeeRows.forEach((emp: any) => {
    emp.slots.forEach((s: any) => {
      if (s.slot_type === 'WORK' && s.process_id) {
        if (!processSlotMap[s.process_id]) processSlotMap[s.process_id] = {};
        if (!processSlotMap[s.process_id][s.time_slot_start]) processSlotMap[s.process_id][s.time_slot_start] = [];
        processSlotMap[s.process_id][s.time_slot_start].push(emp.employee_name);
      }
    });
  });

  const totalCost = employeeRows.reduce((sum: number, emp: any) =>
    sum + emp.slots.reduce((s: number, sl: any) => s + (sl.slot_cost ?? 0), 0), 0);
  const overtimeCost = employeeRows.reduce((sum: number, emp: any) =>
    sum + emp.slots.filter((sl: any) => sl.is_overtime).reduce((s: number, sl: any) => s + (sl.slot_cost ?? 0), 0), 0);

  const getSlot = (emp: any, slot: string) => emp.slots.find((s: any) => s.time_slot_start === slot);
  const empWorkMinutes = (emp: any) => emp.slots.filter((s: any) => s.slot_type === 'WORK').length * 15;
  const empCost = (emp: any) => emp.slots.reduce((s: number, sl: any) => s + (sl.slot_cost ?? 0), 0);

  // 処理フローはバックエンドが唯一の真実として計算する（フロントでの
  // 再シミュレーションは廃止）。/api/shifts/{date}/flow の結果をそのまま表示。
  type FlowRow = {
    slot: string; 発生量累計: number; 処理実績累計: number;
    発生量: number; 処理量: number; 処理残: number;
    最大処理能力: number | null; 稼働率: number | null;
  };
  const simCumData: Record<string, FlowRow[]> = (() => {
    const procData = (shiftFlow as any)?.processes ?? {};
    const out: Record<string, FlowRow[]> = {};
    Object.keys(procData).forEach((pid: string) => {
      out[pid] = (procData[pid] as any[]).map((r: any) => ({
        slot: r.slot,
        発生量累計: r.cum_arrived,
        処理実績累計: r.cum_processed,
        発生量: r.incoming,
        処理量: r.processed,
        処理残: r.backlog,
        最大処理能力: r.capacity ?? null,
        稼働率: r.utilization ?? null,
      }));
    });
    return out;
  })();

  // Group processes by line_type for two separate graphs
  const lineTypeGroups: Record<string, string[]> = {};
  processes.forEach((p: any) => {
    const lt = p.line_type ?? 'OTHER';
    if (!lineTypeGroups[lt]) lineTypeGroups[lt] = [];
    lineTypeGroups[lt].push(p.process_id);
  });
  const LINE_TYPE_LABELS: Record<string, string> = {
    INBOUND: '入庫系',
    OUTBOUND: '出庫系',
  };
  const lineTypes = Object.keys(lineTypeGroups).sort();

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-800 mb-4">シフト生成</h1>
      <div className="flex gap-4 items-end mb-5 flex-wrap">
        <div>
          <label className="block text-xs text-gray-500 mb-1">対象日</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
        </div>
        {shifts && (
          <div className="flex gap-4 text-sm text-gray-700">
            <span>総費用：<strong>¥{totalCost.toLocaleString()}</strong></span>
            <span>残業費：<strong className="text-orange-500">¥{overtimeCost.toLocaleString()}</strong></span>
          </div>
        )}
        <div className="ml-auto flex gap-2">
          <button onClick={() => navigate(`/optimization?date=${date}`)} className="px-4 py-2 border rounded text-sm text-gray-600 hover:bg-gray-50">← 再最適化へ戻る</button>
          <button onClick={handleExport} disabled={downloading || !shifts} className="bg-green-600 text-white px-5 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50">
            {downloading ? 'ダウンロード中...' : 'Excelダウンロード'}
          </button>
        </div>
      </div>

      <div className="flex border-b mb-5">
        <button onClick={() => setTab('employee')} className={`px-4 py-2 text-sm font-medium ${tab === 'employee' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>人別シフト</button>
        <button onClick={() => setTab('process')} className={`px-4 py-2 text-sm font-medium ${tab === 'process' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>工程別シフト</button>
        <button onClick={() => setTab('graph')} className={`px-4 py-2 text-sm font-medium ${tab === 'graph' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500'}`}>稼働グラフ</button>
      </div>

      {!shifts && tab !== 'graph' ? (
        <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
          <p className="mb-2">シフトデータがありません</p>
          <p className="text-sm">配置最適化から案を選択してください</p>
        </div>
      ) : tab === 'employee' ? (
        <div className="bg-white rounded-lg border overflow-auto" style={{ maxHeight: '65vh' }}>
          <table className="text-xs border-collapse">
            <thead className="sticky top-0 bg-white z-10">
              <tr>
                <th className="border px-3 py-2 bg-gray-50 text-left min-w-28 sticky left-0 z-20">人員名</th>
                {allSlots.map((s: string) => (
                  <th key={s} className="border px-1 py-2 bg-gray-50 text-center min-w-12">{s}</th>
                ))}
                <th className="border px-3 py-2 bg-gray-50 text-right min-w-20">実働</th>
                <th className="border px-3 py-2 bg-gray-50 text-right min-w-24">人件費</th>
              </tr>
            </thead>
            <tbody>
              {employeeRows.map((emp: any) => (
                <tr key={emp.employee_id} className="border-b hover:bg-gray-50">
                  <td className="border px-3 py-1.5 font-medium sticky left-0 bg-white">{emp.employee_name}</td>
                  {allSlots.map((slot: string) => {
                    const cell = getSlot(emp, slot);
                    if (!cell) return <td key={slot} className="border px-1 py-1.5" />;
                    const bg =
                      cell.slot_type === 'LUNCH_BREAK' ? 'bg-gray-200' :
                      cell.slot_type === 'LEGAL_BREAK' ? 'bg-gray-300' :
                      cell.slot_type === 'OFF' ? '' :
                      (procColorMap[cell.process_id] ?? 'bg-gray-400');
                    return (
                      <td key={slot} className={`border px-0.5 py-1.5 text-center ${bg} ${cell.is_overtime ? 'ring-2 ring-orange-400 ring-inset' : ''}`}>
                        <span className={cell.slot_type === 'WORK' ? 'text-white' : 'text-gray-600'}>
                          {cell.slot_type === 'WORK' ? (procMap[cell.process_id]?.process_name?.slice(0, 2) ?? '') :
                           cell.slot_type === 'LUNCH_BREAK' ? '昼' :
                           cell.slot_type === 'LEGAL_BREAK' ? '休' : ''}
                        </span>
                      </td>
                    );
                  })}
                  <td className="border px-3 py-1.5 text-right">{(empWorkMinutes(emp) / 60).toFixed(1)}h</td>
                  <td className="border px-3 py-1.5 text-right">¥{empCost(emp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : tab === 'process' ? (
        <div className="bg-white rounded-lg border overflow-auto" style={{ maxHeight: '65vh' }}>
          <table className="text-xs border-collapse">
            <thead className="sticky top-0 bg-white z-10">
              <tr>
                <th className="border px-3 py-2 bg-gray-50 text-left min-w-28 sticky left-0 z-20">工程名</th>
                {allSlots.map((s: string) => (
                  <th key={s} className="border px-1 py-2 bg-gray-50 text-center min-w-12">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {procList.map((pid: string) => {
                const slotData = processSlotMap[pid] ?? {};
                const hasAny = Object.values(slotData).some((names: any) => names.length > 0);
                if (!hasAny) return null;
                return (
                  <tr key={pid} className="border-b hover:bg-gray-50">
                    <td className="border px-3 py-1.5 font-medium sticky left-0 bg-white">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${procColorMap[pid]}`} />
                        {procMap[pid]?.process_name ?? pid}
                      </div>
                    </td>
                    {allSlots.map((slot: string) => {
                      const names: string[] = slotData[slot] ?? [];
                      return (
                        <td key={slot} className={`border px-1 py-1.5 text-center ${names.length > 0 ? 'bg-blue-50' : ''}`}>
                          {names.length > 0 && (
                            <span className="text-xs text-blue-800" title={names.join(', ')}>{names.length}人</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        /* 稼働グラフ：入庫系・出庫系それぞれの累積処理グラフ */
        <div className="space-y-6">
          {lineTypes.length === 0 ? (
            <div className="bg-white rounded-lg border p-12 text-center text-gray-400">
              <p>工程データがありません</p>
            </div>
          ) : lineTypes.map(lt => {
            const pids = lineTypeGroups[lt].filter(pid => simCumData[pid]?.length > 0);
            const label = LINE_TYPE_LABELS[lt] ?? lt;

            // Merge all slots across processes in this line group
            const slotSet = new Set<string>();
            pids.forEach(pid => simCumData[pid].forEach(d => slotSet.add(d.slot)));
            const slots = [...slotSet].sort();

            // Build chart data: one row per slot, columns per process x {発生, 処理}
            const chartData = slots.map(slot => {
              const row: Record<string, any> = { slot };
              pids.forEach((pid) => {
                const name = procMap[pid]?.process_name ?? pid;
                const point = simCumData[pid].find(d => d.slot === slot);
                row[`${name}_発生`] = point?.発生量累計 ?? null;
                row[`${name}_処理`] = point?.処理実績累計 ?? null;
              });
              return row;
            });

            return (
              <div key={lt} className="bg-white rounded-lg border p-4">
                <h3 className="font-semibold text-gray-700 mb-1 text-sm">{label}</h3>
                <div className="mb-2 text-xs text-gray-400 flex gap-4">
                  <span>実線：処理実績累計 　破線：処理発生量累計</span>
                </div>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 60 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="slot" angle={-60} textAnchor="end" tick={{ fontSize: 10 }} interval={1} />
                      <YAxis label={{ value: '累積処理量', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                      <Tooltip formatter={(value: any) => [`${Number(value).toLocaleString()}`]} />
                      <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
                      {pids.map((pid, i) => {
                        const name = procMap[pid]?.process_name ?? pid;
                        const color = CHART_COLORS[i % CHART_COLORS.length];
                        return [
                          <Line key={`${pid}_発生`} type="monotone" dataKey={`${name}_発生`} stroke={color} strokeWidth={1.5} strokeDasharray="5 3" dot={false} name={`${name} 発生累計`} connectNulls />,
                          <Line key={`${pid}_処理`} type="monotone" dataKey={`${name}_処理`} stroke={color} strokeWidth={2} dot={false} name={`${name} 処理累計`} connectNulls />,
                        ];
                      })}
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center text-gray-400 py-8 text-sm">
                    {!shifts ? 'シフトを選択すると処理実績累計が表示されます' : '物量展開を実行してください'}
                  </div>
                )}

                {/* 工程間滞留量（バッファ）グラフ */}
                {chartData.length > 0 && <BufferChart
                  slots={slots}
                  pids={pids}
                  simCumData={simCumData}
                  procMap={procMap}
                  chartColors={CHART_COLORS}
                />}

                {/* 表形式：工程ごとの 発生・処理・残 をスロット単位で表示 */}
                {pids.length > 0 && (
                  <div className="mt-5 space-y-5">
                    {pids.map(pid => {
                      const name = procMap[pid]?.process_name ?? pid;
                      const rows = simCumData[pid] ?? [];
                      if (!rows.length) return null;
                      const last = rows[rows.length - 1];
                      const totalIn = Math.round(last.発生量累計 * 10) / 10;
                      const totalDone = Math.round(last.処理実績累計 * 10) / 10;
                      const remain = Math.round((last.処理残) * 10) / 10;
                      // 当日平均稼働率＝Σ実処理 ÷ Σ最大処理能力（人を配置したスロットのみ）
                      const capSum = rows.reduce((s, r) => s + (r.最大処理能力 ?? 0), 0);
                      const doneOnCap = rows.reduce(
                        (s, r) => s + (r.最大処理能力 != null ? r.処理量 : 0), 0);
                      const avgUtil = capSum > 0 ? doneOnCap / capSum : null;
                      return (
                        <div key={pid} className="border rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between bg-gray-50 px-3 py-2 border-b">
                            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                              <span className={`w-2 h-2 rounded-full ${procColorMap[pid]}`} />
                              {name}
                            </div>
                            <div className="text-xs text-gray-500 flex gap-3">
                              <span>発生計：<strong>{totalIn.toLocaleString()}</strong></span>
                              <span>処理計：<strong>{totalDone.toLocaleString()}</strong></span>
                              <span className={remain > 0.5 ? 'text-red-600' : ''}>未処理残：<strong>{remain.toLocaleString()}</strong></span>
                              <span title="当日平均＝Σ実処理 ÷ Σ最大処理能力（配置スロットのみ）">
                                平均稼働率：<strong>{avgUtil != null ? `${(avgUtil * 100).toFixed(0)}%` : '—'}</strong>
                              </span>
                            </div>
                          </div>
                          <div className="overflow-auto" style={{ maxHeight: '300px' }}>
                            <table className="text-xs border-collapse w-full">
                              <thead className="sticky top-0 bg-white z-10">
                                <tr>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-left">時刻</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right">処理発生</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right" title="配置人員から求まる最大処理能力（個/15分）">最大処理能力</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right">処理量</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right" title="実処理量 ÷ 最大処理能力">稼働率</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right">処理残</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right">発生累計</th>
                                  <th className="border px-2 py-1.5 bg-gray-50 text-right">処理累計</th>
                                </tr>
                              </thead>
                              <tbody>
                                {rows.map(r => (
                                  <tr key={r.slot} className="hover:bg-gray-50">
                                    <td className="border px-2 py-1 font-medium">{r.slot}</td>
                                    <td className="border px-2 py-1 text-right">{r.発生量 > 0 ? r.発生量.toLocaleString() : ''}</td>
                                    <td className="border px-2 py-1 text-right text-gray-500">{r.最大処理能力 != null && r.最大処理能力 > 0 ? r.最大処理能力.toLocaleString() : ''}</td>
                                    <td className="border px-2 py-1 text-right">{r.処理量 > 0 ? r.処理量.toLocaleString() : ''}</td>
                                    <td className={`border px-2 py-1 text-right ${r.稼働率 == null ? 'text-gray-300' : r.稼働率 >= 0.999 ? 'text-green-600' : r.稼働率 < 0.7 ? 'text-orange-500' : 'text-gray-600'}`}>{r.稼働率 != null ? `${(r.稼働率 * 100).toFixed(0)}%` : ''}</td>
                                    <td className={`border px-2 py-1 text-right ${r.処理残 > 0.5 ? 'text-red-600 font-medium' : 'text-gray-400'}`}>{r.処理残 > 0.05 ? r.処理残.toLocaleString() : ''}</td>
                                    <td className="border px-2 py-1 text-right text-gray-500">{r.発生量累計.toLocaleString()}</td>
                                    <td className="border px-2 py-1 text-right text-gray-500">{r.処理実績累計.toLocaleString()}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-blue-500 rounded" /> 工程（色は工程別）</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 bg-gray-200 rounded" /> 昼休憩</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 border-2 border-orange-400 rounded" /> 残業</span>
      </div>
    </div>
  );
}
