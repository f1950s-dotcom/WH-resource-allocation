import type { OptimizationResult } from '../types';
import { useNavigate } from 'react-router-dom';
import { selectOptimizationResult } from '../api/client';

const TYPE_LABELS: Record<string, string> = {
  FASTEST: '案A：最速完了',
  CHEAPEST: '案B：最低コスト',
  LEAST_MOVE: '案C：最小移動',
};

interface Props {
  result: OptimizationResult;
  onSelect?: () => void;
}

export default function OptimizationCard({ result, onSelect }: Props) {
  const navigate = useNavigate();

  const handleSelect = async () => {
    await selectOptimizationResult(result.result_id);
    onSelect?.();
    navigate('/shift');
  };

  return (
    <div className={`bg-white rounded-lg border-2 p-4 flex flex-col gap-3 ${result.is_selected ? 'border-blue-500' : 'border-gray-200'}`}>
      <div className="font-bold text-gray-800">{TYPE_LABELS[result.result_type] || result.result_type}</div>
      <div className="text-xs text-gray-500">算出: {new Date(result.calculated_at).toLocaleString('ja-JP')}</div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="text-gray-600">期限遵守</div>
        <div className={result.is_deadline_met ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'}>
          {result.is_deadline_met ? '✓ 遵守' : '✗ 違反'}
        </div>
        <div className="text-gray-600">総コスト</div>
        <div className="font-semibold">¥{result.total_cost.toLocaleString()}</div>
        <div className="text-gray-600">残業コスト</div>
        <div className="font-semibold text-orange-600">¥{result.total_overtime_cost.toLocaleString()}</div>
        <div className="text-gray-600">工程移動回数</div>
        <div className="font-semibold">{result.total_process_moves}回</div>
      </div>
      {result.deadline_violations && Object.keys(result.deadline_violations).length > 0 && (
        <div className="text-xs text-red-600 bg-red-50 p-2 rounded">
          期限違反: {Object.entries(result.deadline_violations).map(([k, v]) => `${k}: ${v}分遅延`).join(', ')}
        </div>
      )}
      <div className="flex gap-2 mt-2">
        <button
          onClick={() => navigate(`/optimization/${result.result_id}`)}
          className="flex-1 text-sm border border-blue-500 text-blue-600 py-1 rounded hover:bg-blue-50"
        >
          詳細を見る
        </button>
        <button
          onClick={handleSelect}
          className="flex-1 text-sm bg-blue-600 text-white py-1 rounded hover:bg-blue-700"
        >
          この案を選択
        </button>
      </div>
    </div>
  );
}
