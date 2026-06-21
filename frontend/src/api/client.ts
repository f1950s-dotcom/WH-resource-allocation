import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Employees  →  /api/employees
export const getEmployees = () => api.get('/api/employees').then(r => r.data);
export const getEmployee = (id: string) => api.get(`/api/employees/${id}`).then(r => r.data);
export const createEmployee = (data: { name: string; hourly_wage: number }) => api.post('/api/employees', data).then(r => r.data);
export const updateEmployee = (id: string, data: Partial<{ name: string; hourly_wage: number; is_active: boolean }>) => api.put(`/api/employees/${id}`, data).then(r => r.data);
export const deleteEmployee = (id: string) => api.delete(`/api/employees/${id}`).then(r => r.data);

// Employee Skills  →  /api/employees/{id}/skills
export const getEmployeeSkills = (employeeId: string) => api.get(`/api/employees/${employeeId}/skills`).then(r => r.data);
export const updateEmployeeSkills = (employeeId: string, skills: { process_id: string; skill_level: number }[]) => api.put(`/api/employees/${employeeId}/skills`, { skills }).then(r => r.data);

// Work Conditions  →  /api/employees/{id}/conditions
export const getWorkConditions = (employeeId: string) => api.get(`/api/employees/${employeeId}/conditions`).then(r => r.data);
export const updateWorkConditions = (employeeId: string, conditions: object[]) => api.put(`/api/employees/${employeeId}/conditions`, { conditions }).then(r => r.data);

// Processes  →  /api/processes
export const getProcesses = () => api.get('/api/processes').then(r => r.data);
export const createProcess = (data: object) => api.post('/api/processes', data).then(r => r.data);
export const updateProcess = (id: string, data: object) => api.put(`/api/processes/${id}`, data).then(r => r.data);
export const deleteProcess = (id: string) => api.delete(`/api/processes/${id}`).then(r => r.data);

// Process Connections  →  /api/processes/connections
export const getProcessConnections = () => api.get('/api/processes/connections').then(r => r.data);
export const createProcessConnection = (data: { from_process_id: string; to_process_id: string }) => {
  // PUT で接続リストを丸ごと置き換えるAPIに合わせて暫定的にGETして追加
  return api.get('/api/processes/connections').then(r => {
    const existing = r.data as any[];
    const newList = [...existing.map((c: any) => ({ from_process_id: c.from_process_id, to_process_id: c.to_process_id })), data];
    return api.put('/api/processes/connections', { connections: newList }).then(res => res.data);
  });
};
export const deleteProcessConnection = (id: string) => {
  return api.get('/api/processes/connections').then(r => {
    const remaining = (r.data as any[])
      .filter((c: any) => c.connection_id !== id)
      .map((c: any) => ({ from_process_id: c.from_process_id, to_process_id: c.to_process_id }));
    return api.put('/api/processes/connections', { connections: remaining }).then(res => res.data);
  });
};

// Volume Conversion Rules  →  /api/volume-rules
export const getVolumeRules = () => api.get('/api/volume-rules').then(r => r.data);
export const updateVolumeRule = (id: string, data: object) =>
  api.get('/api/volume-rules').then(r => {
    const updated = (r.data as any[]).map((rule: any) =>
      rule.rule_id === id ? { ...rule, ...data } : rule
    );
    return api.put('/api/volume-rules', { rules: updated }).then(res => res.data);
  });
export const createVolumeRule = (data: object) =>
  api.get('/api/volume-rules').then(r => {
    const list = [...(r.data as any[]).map((rule: any) => ({
      source_type: rule.source_type, process_id: rule.process_id,
      conversion_rate: rule.conversion_rate, unit_description: rule.unit_description,
    })), data];
    return api.put('/api/volume-rules', { rules: list }).then(res => res.data);
  });

// Deadline Conditions  →  /api/conditions/deadlines
export const getDeadlineConditions = () => api.get('/api/conditions/deadlines').then(r => r.data);
export const updateDeadlineCondition = (id: string, data: object) =>
  api.get('/api/conditions/deadlines').then(r => {
    const updated = (r.data as any[]).map((d: any) =>
      d.deadline_id === id ? { ...d, ...data } : d
    );
    return api.put('/api/conditions/deadlines', { deadlines: updated }).then(res => res.data);
  });
export const createDeadlineCondition = (data: object) =>
  api.get('/api/conditions/deadlines').then(r => {
    const list = [...(r.data as any[]).map((d: any) => ({
      process_id: d.process_id, must_finish_by: d.must_finish_by, is_active: d.is_active,
    })), data];
    return api.put('/api/conditions/deadlines', { deadlines: list }).then(res => res.data);
  });

// System Conditions  →  /api/conditions/system
export const getSystemConditions = () => api.get('/api/conditions/system').then(r => r.data);
export const updateSystemCondition = (key: string, value: string) =>
  api.get('/api/conditions/system').then(r => {
    const updated = (r.data as any[]).map((s: any) =>
      s.condition_key === key ? { ...s, condition_value: value } : s
    );
    return api.put('/api/conditions/system', { conditions: updated }).then(res => res.data);
  });

// Volume Plans  →  /api/volume-plans/{date}  ※BodyキーはBE側で "entries"
export const getVolumePlans = (date: string) => api.get(`/api/volume-plans/${date}`).then(r => r.data);
export const saveVolumePlans = (date: string, plans: { volume_type: string; time_slot_start: string; volume: number }[]) =>
  api.put(`/api/volume-plans/${date}`, { entries: plans }).then(r => r.data);

// Volume Expansions  →  /api/volume-expansions/{date}
export const getVolumeExpansions = (date: string) => api.get(`/api/volume-expansions/${date}`).then(r => r.data);
export const runVolumeExpansion = (date: string) => api.post(`/api/volume-plans/${date}/expand`).then(r => r.data);

// Optimization  →  /api/optimize/{date}
export const runOptimization = (date: string) => api.post(`/api/optimize/${date}`).then(r => r.data);
export const getOptimizationResults = (date: string) => api.get(`/api/optimize/${date}/results`).then(r => r.data);
export const getOptimizationAssignments = (resultId: string, date?: string) => {
  // date is needed for the route. Fall back to today.
  const d = date ?? new Date().toISOString().slice(0, 10);
  return api.get(`/api/optimize/${d}/results/${resultId}`).then(r => r.data.assignments);
};
export const selectOptimizationResult = (resultId: string, date?: string) => {
  const d = date ?? new Date().toISOString().slice(0, 10);
  return api.post(`/api/optimize/${d}/results/${resultId}/select`).then(r => r.data);
};

// Shifts  →  /api/shifts/{date}
export const getShifts = (date: string) => api.get(`/api/shifts/${date}`).then(r => r.data);
export const exportShifts = (date: string) => api.get(`/api/shifts/${date}/export`, { responseType: 'blob' }).then(r => r.data);

export default api;
