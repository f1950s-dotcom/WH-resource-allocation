import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  { label: 'ホーム', path: '/' },
  {
    label: 'マスタ設定', children: [
      { label: '人員マスタ', path: '/master/employees' },
      { label: '工程マスタ', path: '/master/processes' },
      { label: '物量変換マスタ', path: '/master/volume-rules' },
      { label: '条件マスタ', path: '/master/conditions' },
    ]
  },
  {
    label: '日次業務', children: [
      { label: '物量登録', path: '/volume-plan' },
      { label: '物量展開', path: '/volume-expansion' },
      { label: '配置最適化', path: '/optimization' },
      { label: 'シフト生成', path: '/shift' },
    ]
  },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({ 'マスタ設定': true, '日次業務': true });

  const toggleSection = (label: string) => {
    setOpenSections(prev => ({ ...prev, [label]: !prev[label] }));
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <aside className="w-60 bg-gray-900 text-white flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-sm font-bold text-blue-400">倉庫配置最適化</h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {navItems.map(item => (
            <div key={item.label}>
              {item.children ? (
                <div>
                  <button
                    onClick={() => toggleSection(item.label)}
                    className="w-full flex items-center justify-between px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-white"
                  >
                    {item.label}
                    <span>{openSections[item.label] ? '▾' : '▸'}</span>
                  </button>
                  {openSections[item.label] && (
                    <div>
                      {item.children.map(child => (
                        <Link
                          key={child.path}
                          to={child.path}
                          className={`block px-6 py-2 text-sm hover:bg-gray-700 transition-colors ${location.pathname === child.path ? 'bg-blue-600 text-white' : 'text-gray-300'}`}
                        >
                          {child.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <Link
                  to={item.path!}
                  className={`block px-4 py-2 text-sm hover:bg-gray-700 transition-colors ${location.pathname === item.path ? 'bg-blue-600 text-white' : 'text-gray-300'}`}
                >
                  {item.label}
                </Link>
              )}
            </div>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
