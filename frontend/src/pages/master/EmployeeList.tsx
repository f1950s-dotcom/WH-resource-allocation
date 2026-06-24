import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getEmployees, createEmployee, deleteEmployee, updateEmployee,
  getProcesses, getAllEmployeeSkills, updateEmployeeSkills,
} from '../../api/client';
import type { Employee } from '../../types';

const LEVEL_LABEL: Record<number, string> = { 1: '見習', 2: '一般', 3: '熟練' };
const LEVEL_COLOR: Record<number, string> = {
  1: 'bg-yellow-100 text-yellow-700',
  2: 'bg-blue-100 text-blue-700',
  3: 'bg-green-100 text-green-700',
};

type RowEdit = { name: string; wage: string; skillMap: Record<string, number> };

export default function EmployeeList() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: employees = [], isLoading } = useQuery({ queryKey: ['employees'], queryFn: getEmployees });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });
  const { data: allSkills = {} } = useQuery({ queryKey: ['allSkills'], queryFn: getAllEmployeeSkills });

  // rows currently in edit mode
  const [editing, setEditing] = useState<Record<string, RowEdit>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: '', hourly_wage: '' });

  const createMut = useMutation({
    mutationFn: () => createEmployee({ name: form.name, hourly_wage: Number(form.hourly_wage) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      setShowModal(false);
      setForm({ name: '', hourly_wage: '' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteEmployee(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['allSkills'] });
    },
  });

  const toggleActive = useMutation({
    mutationFn: (emp: Employee) => updateEmployee(emp.employee_id, { is_active: !emp.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['employees'] }),
  });

  const startEdit = (emp: Employee) => {
    const skillMap: Record<string, number> = {};
    const empSkills: { process_id: string; skill_level: number }[] = (allSkills as any)[emp.employee_id] ?? [];
    empSkills.forEach((s: any) => { skillMap[s.process_id] = s.skill_level; });
    setEditing(prev => ({ ...prev, [emp.employee_id]: { name: emp.name, wage: String(emp.hourly_wage), skillMap } }));
  };

  const cancelEdit = (empId: string) => {
    setEditing(prev => { const n = { ...prev }; delete n[empId]; return n; });
  };

  const saveRow = async (emp: Employee) => {
    const row = editing[emp.employee_id];
    if (!row) return;
    setSaving(prev => ({ ...prev, [emp.employee_id]: true }));
    try {
      await updateEmployee(emp.employee_id, { name: row.name, hourly_wage: Number(row.wage) });
      const skillList = Object.entries(row.skillMap)
        .filter(([, lv]) => lv > 0)
        .map(([process_id, skill_level]) => ({ process_id, skill_level }));
      await updateEmployeeSkills(emp.employee_id, skillList);
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['allSkills'] });
      cancelEdit(emp.employee_id);
    } finally {
      setSaving(prev => { const n = { ...prev }; delete n[emp.employee_id]; return n; });
    }
  };

  const setSkillLevel = (empId: string, processId: string, level: number) => {
    setEditing(prev => ({
      ...prev,
      [empId]: { ...prev[empId], skillMap: { ...prev[empId].skillMap, [processId]: level } },
    }));
  };

  const editingCount = Object.keys(editing).length;

  if (isLoading) return <div className="p-6 text-gray-500">読み込み中...</div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-800">人員マスタ</h1>
          {editingCount > 0 && (
            <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded">
              {editingCount}件 編集中
            </span>
          )}
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="bg-blue-600 text-white text-sm px-4 py-2 rounded hover:bg-blue-700"
        >
          + 新規追加
        </button>
      </div>

      <div className="bg-white rounded-lg border overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-3 py-3 text-left text-gray-600 min-w-[120px]">氏名</th>
              <th className="px-3 py-3 text-right text-gray-600 min-w-[90px]">時給</th>
              {processes.map((p: any) => (
                <th key={p.process_id} className="px-3 py-3 text-center text-gray-600 min-w-[80px]">
                  <div className="text-xs">{p.process_name}</div>
                  <div className="text-xs text-gray-400">{p.line_type === 'INBOUND' ? '入庫' : '出庫'}</div>
                </th>
              ))}
              <th className="px-3 py-3 text-center text-gray-600">状態</th>
              <th className="px-3 py-3 text-center text-gray-600 min-w-[160px]">操作</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp: Employee) => {
              const row = editing[emp.employee_id];
              const isEditing = !!row;
              const isSaving = saving[emp.employee_id];
              const empSkills: Record<string, number> = {};
              ((allSkills as any)[emp.employee_id] ?? []).forEach((s: any) => {
                empSkills[s.process_id] = s.skill_level;
              });

              return (
                <tr
                  key={emp.employee_id}
                  className={`border-b ${isEditing ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                >
                  {/* 氏名 */}
                  <td className="px-3 py-2">
                    {isEditing ? (
                      <input
                        value={row.name}
                        onChange={e => setEditing(prev => ({ ...prev, [emp.employee_id]: { ...prev[emp.employee_id], name: e.target.value } }))}
                        className="border rounded px-2 py-1 text-sm w-full"
                      />
                    ) : (
                      <button
                        onClick={() => navigate(`/master/employees/${emp.employee_id}`)}
                        className="text-blue-600 hover:underline text-left"
                      >
                        {emp.name}
                      </button>
                    )}
                  </td>

                  {/* 時給 */}
                  <td className="px-3 py-2 text-right">
                    {isEditing ? (
                      <input
                        type="number"
                        value={row.wage}
                        onChange={e => setEditing(prev => ({ ...prev, [emp.employee_id]: { ...prev[emp.employee_id], wage: e.target.value } }))}
                        className="border rounded px-2 py-1 text-sm w-24 text-right"
                      />
                    ) : (
                      <span>¥{emp.hourly_wage.toLocaleString()}</span>
                    )}
                  </td>

                  {/* 工程別スキル */}
                  {processes.map((p: any) => {
                    const pid = p.process_id;
                    const level = isEditing ? (row.skillMap[pid] ?? 0) : (empSkills[pid] ?? 0);
                    return (
                      <td key={pid} className="px-3 py-2 text-center">
                        {isEditing ? (
                          <select
                            value={level}
                            onChange={e => setSkillLevel(emp.employee_id, pid, Number(e.target.value))}
                            className="border rounded px-1 py-1 text-xs w-full"
                          >
                            <option value={0}>－</option>
                            <option value={1}>1 見習</option>
                            <option value={2}>2 一般</option>
                            <option value={3}>3 熟練</option>
                          </select>
                        ) : level > 0 ? (
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${LEVEL_COLOR[level]}`}>
                            {LEVEL_LABEL[level]}
                          </span>
                        ) : (
                          <span className="text-gray-300 text-xs">－</span>
                        )}
                      </td>
                    );
                  })}

                  {/* 状態 */}
                  <td className="px-3 py-2 text-center">
                    <button
                      onClick={() => toggleActive.mutate(emp)}
                      className={`text-xs px-2 py-1 rounded ${emp.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
                    >
                      {emp.is_active ? '有効' : '無効'}
                    </button>
                  </td>

                  {/* 操作 */}
                  <td className="px-3 py-2 text-center">
                    {isEditing ? (
                      <div className="flex gap-1 justify-center">
                        <button
                          onClick={() => saveRow(emp)}
                          disabled={isSaving}
                          className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                        >
                          {isSaving ? '保存中' : '保存'}
                        </button>
                        <button
                          onClick={() => cancelEdit(emp.employee_id)}
                          className="text-xs px-3 py-1 border rounded text-gray-600 hover:bg-gray-50"
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-1 justify-center">
                        <button
                          onClick={() => startEdit(emp)}
                          className="text-xs px-3 py-1 border border-blue-300 text-blue-600 rounded hover:bg-blue-50"
                        >
                          編集
                        </button>
                        <button
                          onClick={() => navigate(`/master/employees/${emp.employee_id}`)}
                          className="text-xs px-3 py-1 border rounded text-gray-600 hover:bg-gray-50"
                        >
                          詳細
                        </button>
                        <button
                          onClick={() => { if (confirm('削除しますか?')) deleteMut.mutate(emp.employee_id); }}
                          className="text-xs px-2 py-1 text-red-500 hover:text-red-700"
                        >
                          削除
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {employees.length === 0 && (
          <div className="p-8 text-center text-gray-400">人員データがありません</div>
        )}
      </div>

      {/* 凡例 */}
      <div className="mt-3 flex gap-4 text-xs text-gray-500">
        <span>習熟度：</span>
        {Object.entries(LEVEL_LABEL).map(([lv, label]) => (
          <span key={lv} className={`px-2 py-0.5 rounded-full ${LEVEL_COLOR[Number(lv)]}`}>
            {lv} {label}
          </span>
        ))}
        <span className="ml-4 text-gray-400">氏名クリック / 詳細ボタン → 勤務条件などの詳細設定</span>
      </div>

      {/* 新規追加モーダル */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-80">
            <h2 className="font-bold text-lg mb-4">新規人員追加</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">氏名</label>
                <input
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full border rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">時給 (円)</label>
                <input
                  type="number"
                  value={form.hourly_wage}
                  onChange={e => setForm(f => ({ ...f, hourly_wage: e.target.value }))}
                  className="w-full border rounded px-3 py-2 text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 border rounded py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                キャンセル
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.name || !form.hourly_wage}
                className="flex-1 bg-blue-600 text-white rounded py-2 text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                追加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
