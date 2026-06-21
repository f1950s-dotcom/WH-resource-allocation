import type { VolumeExpansion, Process } from '../types';

interface Props {
  expansions: VolumeExpansion[];
  processes: Process[];
}

function getColor(value: number): string {
  if (value === 0) return 'bg-white';
  if (value <= 1) return 'bg-blue-100';
  if (value <= 2) return 'bg-blue-300';
  if (value <= 3) return 'bg-blue-500 text-white';
  return 'bg-blue-800 text-white';
}

export default function HeatMap({ expansions, processes }: Props) {
  if (!expansions.length || !processes.length) return <div className="text-gray-500 text-sm">データがありません</div>;

  const slots = [...new Set(expansions.map(e => e.time_slot_start))].sort();

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0">時間</th>
            {processes.map(p => (
              <th key={p.process_id} className="border border-gray-300 px-2 py-1 bg-gray-50 whitespace-nowrap">{p.process_name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slots.map(slot => (
            <tr key={slot}>
              <td className="border border-gray-300 px-2 py-1 bg-gray-50 sticky left-0 font-mono">{slot}</td>
              {processes.map(p => {
                const e = expansions.find(e => e.time_slot_start === slot && e.process_id === p.process_id);
                const val = e?.required_person_slots ?? 0;
                return (
                  <td key={p.process_id} className={`border border-gray-300 px-2 py-1 text-center ${getColor(val)}`}>
                    {val > 0 ? val.toFixed(1) : ''}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
