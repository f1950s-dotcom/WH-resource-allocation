import type { OptimizationAssignment, Employee, Process } from '../types';

interface Props {
  assignments: OptimizationAssignment[];
  employees: Employee[];
  processes: Process[];
  viewMode: 'employee' | 'process';
}

export default function TimeSlotGrid({ assignments, employees, processes, viewMode }: Props) {
  const slots = [...new Set(assignments.map(a => a.time_slot_start))].sort();

  if (viewMode === 'employee') {
    return (
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0">人員名</th>
              {slots.map(s => <th key={s} className="border border-gray-300 px-1 py-1 bg-gray-50 font-mono">{s.slice(0,5)}</th>)}
            </tr>
          </thead>
          <tbody>
            {employees.map(emp => (
              <tr key={emp.employee_id}>
                <td className="border border-gray-300 px-2 py-1 sticky left-0 bg-white">{emp.name}</td>
                {slots.map(slot => {
                  const a = assignments.find(a => a.employee_id === emp.employee_id && a.time_slot_start === slot);
                  const proc = a?.process_id ? processes.find(p => p.process_id === a.process_id) : null;
                  const label = a?.slot_type === 'LUNCH_BREAK' ? '昼休' : a?.slot_type === 'LEGAL_BREAK' ? '休憩' : a?.slot_type === 'OFF' ? '' : proc?.process_name?.slice(0, 4) || '';
                  const bg = a?.slot_type === 'LUNCH_BREAK' ? 'bg-gray-200' : a?.slot_type === 'LEGAL_BREAK' ? 'bg-gray-100' : a?.slot_type === 'WORK' ? 'bg-blue-100' : '';
                  return <td key={slot} className={`border border-gray-300 px-1 py-1 text-center ${bg}`}>{label}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0">工程名</th>
            {slots.map(s => <th key={s} className="border border-gray-300 px-1 py-1 bg-gray-50 font-mono">{s.slice(0,5)}</th>)}
          </tr>
        </thead>
        <tbody>
          {processes.map(proc => (
            <tr key={proc.process_id}>
              <td className="border border-gray-300 px-2 py-1 sticky left-0 bg-white">{proc.process_name}</td>
              {slots.map(slot => {
                const count = assignments.filter(a => a.process_id === proc.process_id && a.time_slot_start === slot && a.slot_type === 'WORK').length;
                return <td key={slot} className={`border border-gray-300 px-1 py-1 text-center ${count > 0 ? 'bg-green-100' : ''}`}>{count > 0 ? count : ''}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
