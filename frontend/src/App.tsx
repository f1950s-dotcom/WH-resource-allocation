import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Home from './pages/Home';
import EmployeeList from './pages/master/EmployeeList';
import EmployeeDetail from './pages/master/EmployeeDetail';
import ProcessList from './pages/master/ProcessList';
import ProcessConnections from './pages/master/ProcessConnections';
import VolumeRules from './pages/master/VolumeRules';
import Conditions from './pages/master/Conditions';
import VolumePlan from './pages/VolumePlan';
import VolumeExpansion from './pages/VolumeExpansion';
import Optimization from './pages/Optimization';
import OptimizationDetail from './pages/OptimizationDetail';
import Shift from './pages/Shift';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/master/employees" element={<EmployeeList />} />
            <Route path="/master/employees/:id" element={<EmployeeDetail />} />
            <Route path="/master/processes" element={<ProcessList />} />
            <Route path="/master/processes/connections" element={<ProcessConnections />} />
            <Route path="/master/volume-rules" element={<VolumeRules />} />
            <Route path="/master/conditions" element={<Conditions />} />
            <Route path="/volume-plan" element={<VolumePlan />} />
            <Route path="/volume-expansion" element={<VolumeExpansion />} />
            <Route path="/optimization" element={<Optimization />} />
            <Route path="/optimization/:resultId" element={<OptimizationDetail />} />
            <Route path="/shift" element={<Shift />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
