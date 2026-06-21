import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getEmployee, updateEmployee,
  getEmployeeSkills, updateEmployeeSkills,
  getWorkConditions, updateWorkConditions,
  getProcesses,
} from '../../api/client';

const DAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

export default function EmployeeDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: emp } = useQuery({ queryKey: ['employee', id], queryFn: () => getEmployee(id!) });
  const { data: skills = [] } = useQuery({ queryKey: ['skills', id], queryFn: () => getEmployeeSkills(id!) });
  const { data: conditions = [] } = useQuery({ queryKey: ['conditions', id], queryFn: () => getWorkConditions(id!) });
  const { data: processes = [] } = useQuery({ queryKey: ['processes'], queryFn: getProcesses });

  const [name, setName] = useState('');
  const [wage, setWage] = useState('');
  const [skillMap, setSkillMap] = useState<Record<string, number>>({});
  const [condMap, setCondMap] = useState<Record<number, any>>({});

  useEffect(() => {
    if (emp) { setName(emp.name); setWage(String(emp.hourly_wage)); }
  }, [emp]);

  useEffect(() => {
    const m: Record<string, number> = {};
    skills.forEach((s: any) => { m[s.process_id] = s.skill_level; });
    setSkillMap(m);
  }, [skills]);

  useEffect(() => {
    const m: Record<number, any> = {};
    conditions.forEach((c: any) => { m[c.day_of_week] = { ...c }; });
    setCondMap(m);
  }, [conditions]);

  const saveMut = useMutation({
    mutationFn: async () => {
      await updateEmployee(id!, { name, hourly_wage: Number(wage) });
      const skillList = Object.entries(skillMap).map(([process_id, skill_level]) => ({ process_id, skill_level }));
      await updateEmployeeSkills(id!, skillList);
      const condList = Object.entries(condMap).map(([dow, c]) => ({ ...c, day_of_week: Number(dow) }));
      await updateWorkConditions(id!, condList);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['employees'] }); navigate('/master/employees'); },
  });

  const toggleSkill = (processId: string) => {
    setSkillMap(m => {
      if (m[processId]) { const n = { ...m }; delete n[processId]; return n; }
      return { ...m, [processId]: 2 };
    });
  };

  const toggleDay = (dow: number) => {
    setCondMap(m => {
      if (m[dow]) { const n = { ...m }; delete n[dow]; return n; }
      return { ...m, [dow]: { day_of_week: dow, work_start_time: '08:00', work_end_time: '17:00', overtime_available: false, min_work_minutes: 0 } };
    });
  };

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/master/employees')} className="text-gray-500 hover:text-gray-700 text-sm">← 戻る</button>
        <h1 className="text-xl font-bold text-gray-800">人員詳細</h1>
      </div>

      <div className="bg-white rounded-lg border p-5 mb-5">
        <h2 className="font-semibold text-gray-700 mb-4">基本情報</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1">氏名</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">時給 (円)</label>
            <input type="number" value={wage} onChange={e => setWage(e.target.value)} className="w-full border rounded px-3 py-2 text-sm" />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border p-5 mb-5">
        <h2 className="font-semibold text-gray-700 mb-4">スキル設定</h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-3 py-2 text-left text-gray-600">工程名</th>
              <th className="px-3 py-2 text-left text-gray-600">ライン</th>
              <th className="px-3 py-2 text-center text-gray-600">対応可否</th>
              <th className="px-3 py-2 text-center text-gray-600">習熟レベル</th>
            </tr>
          </thead>
          <tbody>
            {processes.map((p: any) => (
              <tr key={p.process_id} className="border-b">
                <td className="px-3 py-2">{p.process_name}</td>
                <td className="px-3 py-2 text-xs text-gray-500">{p.line_type === 'INBOUND' ? '入庫' : '出庫'}</td>
                <td className="px-3 py-2 text-center">
                  <input type="checkbox" checked={!!skillMap[p.process_id]} onChange={() => toggleSkill(p.process_id)} className="w-4 h-4" />
                </td>
                <td className="px-3 py-2 text-center">
                  {skillMap[p.process_id] && (
                    <div className="flex gap-3 justify-center">
                      {[1, 2, 3].map(lv => (
                        <label key={lv} className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="radio"
                            name={`skill-${p.process_id}`}
                            checked={skillMap[p.process_id] === lv}
                            onChange={() => setSkillMap(m => ({ ...m, [p.process_id]: lv }))}
                            className="w-3 h-3"
                          />
                          <span className="text-xs">{lv}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-lg border p-5 mb-5">
        <h2 className="font-semibold text-gray-700 mb-4">勤務条件（曜日別）</h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-3 py-2 text-left">曜日</th>
              <th className="px-3 py-2 text-center">出勤</th>
              <th className="px-3 py-2 text-center">開始</th>
              <th className="px-3 py-2 text-center">終了</th>
              <th className="px-3 py-2 text-center">残業可</th>
              <th className="px-3 py-2 text-center">最低労働(分)</th>
            </tr>
          </thead>
          <tbody>
            {DAY_LABELS.map((label, dow) => (
              <tr key={dow} className="border-b">
                <td className="px-3 py-2 font-medium">{label}</td>
                <td className="px-3 py-2 text-center">
                  <input type="checkbox" checked={!!condMap[dow]} onChange={() => toggleDay(dow)} className="w-4 h-4" />
                </td>
                {condMap[dow] ? (
                  <>
                    <td className="px-3 py-2">
                      <input type="time" value={condMap[dow].work_start_time} onChange={e => setCondMap(m => ({ ...m, [dow]: { ...m[dow], work_start_time: e.target.value } }))} className="border rounded px-2 py-1 text-xs w-24" />
                    </td>
                    <td className="px-3 py-2">
                      <input type="time" value={condMap[dow].work_end_time} onChange={e => setCondMap(m => ({ ...m, [dow]: { ...m[dow], work_end_time: e.target.value } }))} className="border rounded px-2 py-1 text-xs w-24" />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <input type="checkbox" checked={condMap[dow].overtime_available} onChange={e => setCondMap(m => ({ ...m, [dow]: { ...m[dow], overtime_available: e.target.checked } }))} className="w-4 h-4" />
                    </td>
                    <td className="px-3 py-2">
                      <input type="number" value={condMap[dow].min_work_minutes} onChange={e => setCondMap(m => ({ ...m, [dow]: { ...m[dow], min_work_minutes: Number(e.target.value) } }))} className="border rounded px-2 py-1 text-xs w-20" />
                    </td>
                  </>
                ) : (
                  <td colSpan={4} className="px-3 py-2 text-center text-gray-300 text-xs">休み</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex gap-3">
        <button onClick={() => navigate('/master/employees')} className="px-6 py-2 border rounded text-sm text-gray-600 hover:bg-gray-50">キャンセル</button>
        <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending} className="px-6 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {saveMut.isPending ? '保存中...' : '保存'}
        </button>
      </div>
    </div>
  );
}
