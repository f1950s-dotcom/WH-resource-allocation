import type { OptimizationAssignment, Employee, Process } from '../types';

const PROCESS_COLORS = [
  'bg-blue-400', 'bg-green-400', 'bg-yellow-400', 'bg-red-400',
  'bg-purple-400', 'bg-pink-400', 'bg-indigo-400', 'bg-orange-400',
  'bg-teal-400', 'bg-cyan-400',
];

interface Props {
  assignments: OptimizationAssignment[];
  employees: Employee[];
  processes: Process[];
}

export default function GanttChart({ assignments, employees, processes }: Props) {
  if (!assignments.length) return <div className="text-gray-500 text-sm">データがありません</div>;

  const slots = [...new Set(assignments.map(a => a.time_slot_start))].sort();
  const processColorMap = new Map(processes.map((p, i) => [p.process_id, PROCESS_COLORS[i % PROCESS_COLORS.length]]));

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0 min-w-24">人員</th>
            {slots.map(slot => (
              <th key={slot} className="border border-gray-300 px-1 py-1 bg-gray-50 font-mono text-center min-w-12">{slot.slice(0, 5)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {employees.map(emp => (
            <tr key={emp.employee_id}>
              <td className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0 whitespace-nowrap">{emp.name}</td>
              {slots.map(slot => {
                const a = assignments.find(a => a.employee_id === emp.employee_id && a.time_slot_start === slot);
                if (!a) return <td key={slot} className="border border-gray-300 px-1 py-1" />;

                let cellClass = '';
                let label = '';
                if (a.slot_type === 'LUNCH_BREAK') { cellClass = 'bg-gray-300'; label = '昼'; }
                else if (a.slot_type === 'LEGAL_BREAK') { cellClass = 'bg-gray-200'; label = '休'; }
                else if (a.slot_type === 'OFF') { cellClass = 'bg-gray-100'; label = ''; }
                else if (a.process_id) {
                  const proc = processes.find(p => p.process_id === a.process_id);
                  cellClass = processColorMap.get(a.process_id) || 'bg-gray-400';
                  label = proc?.process_name?.slice(0, 2) || '';
                }

                return (
                  <td key={slot} className={`border px-1 py-1 text-center text-xs ${cellClass} ${a.is_overtime ? 'ring-2 ring-orange-500' : 'border-gray-300'}`}>
                    {label}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex flex-wrap gap-2">
        {processes.map((p, i) => (
          <div key={p.process_id} className="flex items-center gap-1">
            <div className={`w-4 h-4 rounded ${PROCESS_COLORS[i % PROCESS_COLORS.length]}`} />
            <span className="text-xs">{p.process_name}</span>
          </div>
        ))}
        <div className="flex items-center gap-1"><div className="w-4 h-4 rounded bg-gray-300" /><span className="text-xs">昼休憩</span></div>
        <div className="flex items-center gap-1"><div className="w-4 h-4 rounded bg-gray-200" /><span className="text-xs">法定休憩</span></div>
        <div className="flex items-center gap-1"><div className="w-4 h-4 rounded ring-2 ring-orange-500" /><span className="text-xs">残業</span></div>
      </div>
    </div>
  );
}
