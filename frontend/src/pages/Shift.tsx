import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getShifts, exportShifts, getProcesses, getVolumeExpansions, getProcessConnections, getVolumeRules, getVolumePlans } from '../api/client';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

const today = () => new Date().toISOString().slice(0, 10);

const PROCESS_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-purple-500',
  'bg-pink-500', 'bg-indigo-500', 'bg-red-500', 'bg-teal-500',
];
const CHART_COLORS = ['#3b82f6', '#22c55e', '#eab308', '#a855f7', '#ec4899', '#6366f1', '#ef4444', '#14b8a6'];

export default function Shift() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [date, setDate] = useState(params.get('date') ?? today());
  const [tab, setTab] = useState<'employee' | 'process' | 'graph'>('employee');
  const [graphProcess, setGraphProcess] = useState<string>('');
  const [downloading, setDownloading] = useState(false);

  const { data: shifts } = useQuery({ queryKey: ['shifts', date], queryFn: () => getShifts(date) });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: expansions = [] } = useQuery({ queryKey: ['expansions', date], queryFn: () => getVolumeExpansions(date) });
  const { data: connections = [] } = useQuery({ queryKey: ['connections'], queryFn: getProcessConnections });
  const { data: volumeRules = [] } = useQuery({ queryKey: ['volumeRules'], queryFn: getVolumeRules });
  const { data: volumePlans = [] } = useQuery({ queryKey: ['volumePlans', date], queryFn: () => getVolumePlans(date) });

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

  // Build upstream map and topological order for flow simulation
  const upstreamOf: Record<string, string> = Object.fromEntries(
    (connections as any[]).map((c: any) => [c.to_process_id, c.from_process_id])
  );
  const ruleMap: Record<string, { source_type: string; rate: number }> = Object.fromEntries(
    (volumeRules as any[]).map((r: any) => [r.process_id, { source_type: r.source_type, rate: Number(r.conversion_rate) }])
  );

  function topoSort(pids: string[], upOf: Record<string, string>): string[] {
    const visited = new Set<string>();
    const order: string[] = [];
    function visit(pid: string) {
      if (visited.has(pid)) return;
      visited.add(pid);
      const up = upOf[pid];
      if (up && pids.includes(up)) visit(up);
      order.push(pid);
    }
    pids.forEach(visit);
    return order;
  }

  // Assignment-based flow simulation across all processes
  const simulationData: Record<string, Array<{ slot: string; 必要人員: number; 配置人員: number; 処理量: number; 処理残量: number }>> = (() => {
    const activePids = processes.map((p: any) => p.process_id);
    if (!activePids.length || !volumePlans.length) return {};

    const procOrder = topoSort(activePids, upstreamOf);

    // plan_map: (source_type, slot) -> volume
    const planMap: Record<string, number> = {};
    (volumePlans as any[]).forEach((vp: any) => {
      planMap[`${vp.volume_type}__${vp.time_slot_start}`] = Number(vp.volume);
    });

    // assigned count per process per slot
    const assignedCount: Record<string, Record<string, number>> = {};
    activePids.forEach((pid: string) => { assignedCount[pid] = {}; });
    employeeRows.forEach((emp: any) => {
      emp.slots.forEach((s: any) => {
        if (s.slot_type === 'WORK' && s.process_id) {
          assignedCount[s.process_id][s.time_slot_start] = (assignedCount[s.process_id][s.time_slot_start] ?? 0) + 1;
        }
      });
    });

    const procMap2: Record<string, any> = Object.fromEntries(processes.map((p: any) => [p.process_id, p]));

    // Collect all slots
    const allSlotsSet = new Set<string>();
    (volumePlans as any[]).forEach((vp: any) => allSlotsSet.add(vp.time_slot_start));
    Object.values(assignedCount).forEach(m => Object.keys(m).forEach(s => allSlotsSet.add(s)));
    const allSlotsSorted = [...allSlotsSet].sort();

    const SLOT_H = 15.0 / 60.0;
    const backlog: Record<string, number> = Object.fromEntries(activePids.map((pid: string) => [pid, 0]));
    const throughput: Record<string, Record<string, number>> = Object.fromEntries(activePids.map((pid: string) => [pid, {}]));
    const result: Record<string, Array<{ slot: string; 必要人員: number; 配置人員: number; 処理量: number; 処理残量: number }>> = {};
    activePids.forEach((pid: string) => { result[pid] = []; });

    for (let idx = 0; idx < allSlotsSorted.length; idx++) {
      const slot = allSlotsSorted[idx];
      const prevSlot = idx > 0 ? allSlotsSorted[idx - 1] : null;

      for (const pid of procOrder) {
        const proc = procMap2[pid];
        if (!proc) continue;
        const bp = Number(proc.base_productivity);
        const rule = ruleMap[pid];
        const isRoot = !upstreamOf[pid] || !activePids.includes(upstreamOf[pid]);

        let incoming = 0;
        if (isRoot) {
          const src = rule?.source_type;
          incoming = src ? (planMap[`${src}__${slot}`] ?? 0) * (rule?.rate ?? 1) : 0;
        } else {
          const up = upstreamOf[pid];
          const upPrevThroughput = prevSlot ? (throughput[up]?.[prevSlot] ?? 0) : 0;
          incoming = upPrevThroughput * (rule?.rate ?? 1);
        }

        backlog[pid] += incoming;
        const workPresent = backlog[pid];
        const cnt = assignedCount[pid][slot] ?? 0;
        const actualThroughput = Math.min(workPresent, cnt * bp * SLOT_H);
        backlog[pid] = workPresent - actualThroughput;
        throughput[pid][slot] = actualThroughput;

        const requiredPersonSlots = bp > 0 ? workPresent / (bp * SLOT_H) : 0;

        if (workPresent > 0 || cnt > 0) {
          result[pid].push({
            slot,
            必要人員: Math.round(requiredPersonSlots * 10) / 10,
            配置人員: cnt,
            処理量: Math.round(actualThroughput * 10) / 10,
            処理残量: Math.round(backlog[pid] * 10) / 10,
          });
        }
      }
    }
    return result;
  })();

  const simProcIds = Object.keys(simulationData).filter(pid => simulationData[pid].length > 0);
  const expansionProcIds = simProcIds.length ? simProcIds : [...new Set(expansions.map((e: any) => e.process_id as string))] as string[];
  const selectedProc = graphProcess || expansionProcIds[0] || '';

  const graphData = simulationData[selectedProc] ?? [];

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
        /* 稼働グラフ */
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-sm text-gray-600">工程：</span>
            <div className="flex gap-2 flex-wrap">
              {expansionProcIds.map((pid, i) => (
                <button
                  key={pid}
                  onClick={() => setGraphProcess(pid)}
                  className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${selectedProc === pid ? 'text-white border-transparent' : 'text-gray-600 bg-white'}`}
                  style={selectedProc === pid ? { backgroundColor: CHART_COLORS[i % CHART_COLORS.length] } : {}}
                >
                  {procMap[pid]?.process_name ?? pid}
                </button>
              ))}
            </div>
          </div>

          {graphData.length > 0 && selectedProc ? (
            <>
              <div className="mb-2 text-xs text-gray-500 flex gap-4 flex-wrap">
                <span><span className="font-medium">必要人員</span>：そのスロットの作業量を捌くのに必要な人数</span>
                <span><span className="font-medium">配置人員</span>：実際に配置された人数</span>
                <span><span className="font-medium">処理残量</span>：配置人員で処理後の積み残し物量（配置ベース）</span>
              </div>
              <ResponsiveContainer width="100%" height={380}>
                <ComposedChart data={graphData} margin={{ top: 5, right: 20, left: 10, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="slot" angle={-60} textAnchor="end" tick={{ fontSize: 10 }} interval={1} />
                  <YAxis yAxisId="left" label={{ value: '人員数', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" label={{ value: '積み残し量', angle: 90, position: 'insideRight', fontSize: 11 }} />
                  <Tooltip formatter={(value: any, name: string) => [
                    (name === '処理残量' || name === '処理量') ? `${Number(value).toLocaleString()} 個` : `${value} 人`,
                    name,
                  ]} />
                  <Legend verticalAlign="top" />
                  <Bar yAxisId="left" dataKey="必要人員" fill="#bfdbfe" name="必要人員" />
                  <Bar yAxisId="left" dataKey="配置人員" fill="#3b82f6" name="配置人員" />
                  <Line yAxisId="right" type="monotone" dataKey="処理量" stroke="#22c55e" strokeWidth={2} dot={false} name="処理量" />
                  <Line yAxisId="right" type="monotone" dataKey="処理残量" stroke="#ef4444" strokeWidth={2} dot={false} name="処理残量" />
                </ComposedChart>
              </ResponsiveContainer>
            </>
          ) : (
            <div className="text-center text-gray-400 py-12">
              <p>物量展開データがありません</p>
              <p className="text-sm mt-1">物量展開を実行してください</p>
            </div>
          )}
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
