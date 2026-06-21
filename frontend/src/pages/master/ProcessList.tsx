import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getProcesses, createProcess, updateProcess, deleteProcess } from '../../api/client';

const LINE_LABEL: Record<string, string> = { INBOUND: '入庫', OUTBOUND: '出庫' };

export default function ProcessList() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: processes = [], isLoading } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<any>(null);
  const [form, setForm] = useState({ process_name: '', line_type: 'INBOUND', base_productivity: '', buffer_capacity: '0', display_order: '0' });

  const openNew = () => { setEditTarget(null); setForm({ process_name: '', line_type: 'INBOUND', base_productivity: '', buffer_capacity: '0', display_order: '0' }); setShowModal(true); };
  const openEdit = (p: any) => { setEditTarget(p); setForm({ process_name: p.process_name, line_type: p.line_type, base_productivity: String(p.base_productivity), buffer_capacity: String(p.buffer_capacity), display_order: String(p.display_order) }); setShowModal(true); };

  const saveMut = useMutation({
    mutationFn: () => {
      const data = { process_name: form.process_name, line_type: form.line_type, base_productivity: Number(form.base_productivity), buffer_capacity: Number(form.buffer_capacity), display_order: Number(form.display_order) };
      return editTarget ? updateProcess(editTarget.process_id, data) : createProcess(data);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['processes'] }); setShowModal(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProcess(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processes'] }),
  });

  if (isLoading) return <div className="p-6 text-gray-500">読み込み中...</div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-bold text-gray-800">工程マスタ</h1>
        <div className="flex gap-2">
          <button onClick={() => navigate('/master/processes/connections')} className="border border-gray-300 text-sm px-4 py-2 rounded hover:bg-gray-50">工程接続設定</button>
          <button onClick={openNew} className="bg-blue-600 text-white text-sm px-4 py-2 rounded hover:bg-blue-700">+ 新規追加</button>
        </div>
      </div>
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-gray-600">工程名</th>
              <th className="px-4 py-3 text-left text-gray-600">ライン</th>
              <th className="px-4 py-3 text-right text-gray-600">基準生産性 (個/人時)</th>
              <th className="px-4 py-3 text-right text-gray-600">バッファ (個)</th>
              <th className="px-4 py-3 text-center text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {processes.map((p: any) => (
              <tr key={p.process_id} className="border-b hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">{p.process_name}</td>
                <td className="px-4 py-3"><span className={`text-xs px-2 py-1 rounded ${p.line_type === 'INBOUND' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>{LINE_LABEL[p.line_type]}</span></td>
                <td className="px-4 py-3 text-right">{p.base_productivity}</td>
                <td className="px-4 py-3 text-right">{p.buffer_capacity}</td>
                <td className="px-4 py-3 text-center flex gap-2 justify-center">
                  <button onClick={() => openEdit(p)} className="text-blue-500 hover:text-blue-700 text-xs">編集</button>
                  <button onClick={() => { if (confirm('削除しますか?')) deleteMut.mutate(p.process_id); }} className="text-red-500 hover:text-red-700 text-xs">削除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {processes.length === 0 && <div className="p-8 text-center text-gray-400">工程データがありません</div>}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96">
            <h2 className="font-bold text-lg mb-4">{editTarget ? '工程編集' : '新規工程追加'}</h2>
            <div className="space-y-3">
              <div><label className="block text-sm text-gray-600 mb-1">工程名</label><input value={form.process_name} onChange={e => setForm(f => ({ ...f, process_name: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" /></div>
              <div><label className="block text-sm text-gray-600 mb-1">ラインタイプ</label>
                <select value={form.line_type} onChange={e => setForm(f => ({ ...f, line_type: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm">
                  <option value="INBOUND">入庫</option>
                  <option value="OUTBOUND">出庫</option>
                </select>
              </div>
              <div><label className="block text-sm text-gray-600 mb-1">基準生産性 (個/人時)</label><input type="number" value={form.base_productivity} onChange={e => setForm(f => ({ ...f, base_productivity: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" /></div>
              <div><label className="block text-sm text-gray-600 mb-1">バッファ容量 (個)</label><input type="number" value={form.buffer_capacity} onChange={e => setForm(f => ({ ...f, buffer_capacity: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" /></div>
              <div><label className="block text-sm text-gray-600 mb-1">表示順</label><input type="number" value={form.display_order} onChange={e => setForm(f => ({ ...f, display_order: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" /></div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowModal(false)} className="flex-1 border rounded py-2 text-sm text-gray-600">キャンセル</button>
              <button onClick={() => saveMut.mutate()} className="flex-1 bg-blue-600 text-white rounded py-2 text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
