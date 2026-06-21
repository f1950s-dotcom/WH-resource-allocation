import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getEmployees, createEmployee, deleteEmployee, updateEmployee } from '../../api/client';
import type { Employee } from '../../types';

export default function EmployeeList() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: employees = [], isLoading } = useQuery({ queryKey: ['employees'], queryFn: getEmployees });
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: '', hourly_wage: '' });

  const createMut = useMutation({
    mutationFn: () => createEmployee({ name: form.name, hourly_wage: Number(form.hourly_wage) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['employees'] }); setShowModal(false); setForm({ name: '', hourly_wage: '' }); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteEmployee(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['employees'] }),
  });

  const toggleActive = useMutation({
    mutationFn: (emp: Employee) => updateEmployee(emp.employee_id, { is_active: !emp.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['employees'] }),
  });

  if (isLoading) return <div className="p-6 text-gray-500">読み込み中...</div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-bold text-gray-800">人員マスタ</h1>
        <button onClick={() => setShowModal(true)} className="bg-blue-600 text-white text-sm px-4 py-2 rounded hover:bg-blue-700">+ 新規追加</button>
      </div>
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-gray-600">氏名</th>
              <th className="px-4 py-3 text-right text-gray-600">時給</th>
              <th className="px-4 py-3 text-center text-gray-600">状態</th>
              <th className="px-4 py-3 text-center text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp: Employee) => (
              <tr key={emp.employee_id} className="border-b hover:bg-gray-50">
                <td className="px-4 py-3">
                  <button onClick={() => navigate(`/master/employees/${emp.employee_id}`)} className="text-blue-600 hover:underline">{emp.name}</button>
                </td>
                <td className="px-4 py-3 text-right">¥{emp.hourly_wage.toLocaleString()}</td>
                <td className="px-4 py-3 text-center">
                  <button onClick={() => toggleActive.mutate(emp)} className={`text-xs px-2 py-1 rounded ${emp.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {emp.is_active ? '有効' : '無効'}
                  </button>
                </td>
                <td className="px-4 py-3 text-center">
                  <button onClick={() => { if (confirm('削除しますか?')) deleteMut.mutate(emp.employee_id); }} className="text-red-500 hover:text-red-700 text-xs">削除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {employees.length === 0 && <div className="p-8 text-center text-gray-400">人員データがありません</div>}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-80">
            <h2 className="font-bold text-lg mb-4">新規人員追加</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">氏名</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">時給 (円)</label>
                <input type="number" value={form.hourly_wage} onChange={e => setForm(f => ({ ...f, hourly_wage: e.target.value }))} className="w-full border rounded px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowModal(false)} className="flex-1 border rounded py-2 text-sm text-gray-600 hover:bg-gray-50">キャンセル</button>
              <button onClick={() => createMut.mutate()} className="flex-1 bg-blue-600 text-white rounded py-2 text-sm hover:bg-blue-700">追加</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
