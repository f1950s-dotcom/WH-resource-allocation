import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getProcesses, getProcessConnections, createProcessConnection, deleteProcessConnection } from '../../api/client';

export default function ProcessConnections() {
  const qc = useQueryClient();
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: connections = [] } = useQuery({ queryKey: ['connections'], queryFn: getProcessConnections });
  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');

  const addMut = useMutation({
    mutationFn: () => createProcessConnection({ from_process_id: fromId, to_process_id: toId }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['connections'] }); setFromId(''); setToId(''); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProcessConnection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connections'] }),
  });

  const procMap = Object.fromEntries(processes.map((p: any) => [p.process_id, p]));

  const inbound = processes.filter((p: any) => p.line_type === 'INBOUND');
  const outbound = processes.filter((p: any) => p.line_type === 'OUTBOUND');

  const renderChain = (procs: any[]) => {
    const ids = procs.map((p: any) => p.process_id);
    const ordered: any[] = [];
    const toIds = new Set(connections.map((c: any) => c.to_process_id));
    const roots = procs.filter((p: any) => !toIds.has(p.process_id));
    const visit = (id: string) => {
      const p = procMap[id];
      if (!p || !ids.includes(id)) return;
      ordered.push(p);
      const next = connections.find((c: any) => c.from_process_id === id && ids.includes(c.to_process_id));
      if (next) visit(next.to_process_id);
    };
    roots.forEach(r => visit(r.process_id));
    procs.filter(p => !ordered.find(o => o.process_id === p.process_id)).forEach(p => ordered.push(p));
    return ordered;
  };

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-bold text-gray-800 mb-6">工程接続設定</h1>

      <div className="grid grid-cols-2 gap-6 mb-6">
        {[{ label: '入庫ライン', procs: inbound }, { label: '出庫ライン', procs: outbound }].map(({ label, procs }) => (
          <div key={label} className="bg-white rounded-lg border p-4">
            <h2 className="font-semibold text-gray-700 mb-3">{label}</h2>
            {renderChain(procs).map((p: any, i: number, arr: any[]) => (
              <div key={p.process_id}>
                <div className={`border rounded px-3 py-2 text-sm text-center ${!connections.find((c: any) => c.to_process_id === p.process_id) && connections.find((c: any) => c.from_process_id === p.process_id) === undefined ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
                  {p.process_name}
                  {!connections.find((c: any) => c.from_process_id === p.process_id && arr.map(a => a.process_id).includes(c.to_process_id)) &&
                    <span className="ml-2 text-xs text-green-600">← 末端</span>}
                </div>
                {i < arr.length - 1 && connections.find((c: any) => c.from_process_id === p.process_id && c.to_process_id === arr[i + 1]?.process_id) &&
                  <div className="text-center text-gray-400 text-lg">↓</div>}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-lg border p-5 mb-5">
        <h2 className="font-semibold text-gray-700 mb-4">接続を追加</h2>
        <div className="flex gap-3 items-center">
          <select value={fromId} onChange={e => setFromId(e.target.value)} className="flex-1 border rounded px-3 py-2 text-sm">
            <option value="">前工程を選択</option>
            {processes.map((p: any) => <option key={p.process_id} value={p.process_id}>{p.process_name}</option>)}
          </select>
          <span className="text-gray-500">→</span>
          <select value={toId} onChange={e => setToId(e.target.value)} className="flex-1 border rounded px-3 py-2 text-sm">
            <option value="">後工程を選択</option>
            {processes.map((p: any) => <option key={p.process_id} value={p.process_id}>{p.process_name}</option>)}
          </select>
          <button onClick={() => addMut.mutate()} disabled={!fromId || !toId} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-40">追加</button>
        </div>
      </div>

      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-gray-600">前工程</th>
              <th className="px-4 py-3 text-left text-gray-600">後工程</th>
              <th className="px-4 py-3 text-center text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {connections.map((c: any) => (
              <tr key={c.connection_id} className="border-b">
                <td className="px-4 py-3">{procMap[c.from_process_id]?.process_name ?? c.from_process_id}</td>
                <td className="px-4 py-3">{procMap[c.to_process_id]?.process_name ?? c.to_process_id}</td>
                <td className="px-4 py-3 text-center">
                  <button onClick={() => deleteMut.mutate(c.connection_id)} className="text-red-500 hover:text-red-700 text-xs">削除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {connections.length === 0 && <div className="p-6 text-center text-gray-400 text-sm">接続が登録されていません</div>}
      </div>
    </div>
  );
}
