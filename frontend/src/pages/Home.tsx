import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getVolumePlans, getVolumeExpansions, getOptimizationResults, getShifts } from '../api/client';

export default function Home() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));

  const { data: plans } = useQuery({ queryKey: ['volumePlans', date], queryFn: () => getVolumePlans(date), enabled: !!date });
  const { data: expansions } = useQuery({ queryKey: ['expansions', date], queryFn: () => getVolumeExpansions(date), enabled: !!date });
  const { data: results } = useQuery({ queryKey: ['results', date], queryFn: () => getOptimizationResults(date), enabled: !!date });
  const { data: shifts } = useQuery({ queryKey: ['shifts', date], queryFn: () => getShifts(date), enabled: !!date });

  const hasPlans = plans && plans.length > 0;
  const hasExpansions = expansions && expansions.length > 0;
  const hasResults = results && results.length > 0;
  const hasShifts = shifts && shifts.length > 0;

  const steps = [
    { label: '物量登録', done: hasPlans, path: '/volume-plan', desc: '入出庫物量を時間帯別に登録' },
    { label: '物量展開', done: hasExpansions, path: '/volume-expansion', desc: '工程別必要人員数を算出' },
    { label: '配置最適化', done: hasResults, path: '/optimization', desc: '3案の最適配置を生成' },
    { label: 'シフト生成', done: hasShifts, path: '/shift', desc: '確定シフトをダウンロード' },
  ];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">倉庫人員配置最適化</h1>
      <div className="mb-6 flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700">対象日</label>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded px-3 py-1.5 text-sm" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {steps.map((step, i) => (
          <div key={step.label} className={`bg-white rounded-lg border-2 p-4 ${step.done ? 'border-green-400' : 'border-gray-200'}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${step.done ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-600'}`}>{i + 1}</span>
              <span className="font-semibold text-gray-800">{step.label}</span>
            </div>
            <p className="text-xs text-gray-500 mb-3">{step.desc}</p>
            <div className={`text-xs font-medium mb-3 ${step.done ? 'text-green-600' : 'text-gray-400'}`}>
              {step.done ? '✓ 完了' : '未実施'}
            </div>
            <Link to={`${step.path}?date=${date}`} className="block text-center text-sm bg-blue-600 text-white py-1.5 rounded hover:bg-blue-700">
              開く
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
