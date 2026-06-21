import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Employees
export const getEmployees = () => api.get('/api/employees').then(r => r.data);
export const getEmployee = (id: string) => api.get(`/api/employees/${id}`).then(r => r.data);
export const createEmployee = (data: { name: string; hourly_wage: number }) => api.post('/api/employees', data).then(r => r.data);
export const updateEmployee = (id: string, data: Partial<{ name: string; hourly_wage: number; is_active: boolean }>) => api.put(`/api/employees/${id}`, data).then(r => r.data);
export const deleteEmployee = (id: string) => api.delete(`/api/employees/${id}`).then(r => r.data);

// Employee Skills
export const getEmployeeSkills = (employeeId: string) => api.get(`/api/employees/${employeeId}/skills`).then(r => r.data);
export const updateEmployeeSkills = (employeeId: string, skills: { process_id: string; skill_level: number }[]) => api.put(`/api/employees/${employeeId}/skills`, { skills }).then(r => r.data);

// Work Conditions
export const getWorkConditions = (employeeId: string) => api.get(`/api/employees/${employeeId}/conditions`).then(r => r.data);
export const updateWorkConditions = (employeeId: string, conditions: object[]) => api.put(`/api/employees/${employeeId}/conditions`, { conditions }).then(r => r.data);

// Processes
export const getProcesses = () => api.get('/api/processes').then(r => r.data);
export const createProcess = (data: object) => api.post('/api/processes', data).then(r => r.data);
export const updateProcess = (id: string, data: object) => api.put(`/api/processes/${id}`, data).then(r => r.data);
export const deleteProcess = (id: string) => api.delete(`/api/processes/${id}`).then(r => r.data);

// Process Connections
export const getProcessConnections = () => api.get('/api/process-connections').then(r => r.data);
export const createProcessConnection = (data: { from_process_id: string; to_process_id: string }) => api.post('/api/process-connections', data).then(r => r.data);
export const deleteProcessConnection = (id: string) => api.delete(`/api/process-connections/${id}`).then(r => r.data);

// Volume Conversion Rules
export const getVolumeRules = () => api.get('/api/volume-conversion-rules').then(r => r.data);
export const updateVolumeRule = (id: string, data: object) => api.put(`/api/volume-conversion-rules/${id}`, data).then(r => r.data);
export const createVolumeRule = (data: object) => api.post('/api/volume-conversion-rules', data).then(r => r.data);

// Deadline Conditions
export const getDeadlineConditions = () => api.get('/api/deadline-conditions').then(r => r.data);
export const updateDeadlineCondition = (id: string, data: object) => api.put(`/api/deadline-conditions/${id}`, data).then(r => r.data);
export const createDeadlineCondition = (data: object) => api.post('/api/deadline-conditions', data).then(r => r.data);

// System Conditions
export const getSystemConditions = () => api.get('/api/system-conditions').then(r => r.data);
export const updateSystemCondition = (key: string, value: string) => api.put(`/api/system-conditions/${key}`, { value }).then(r => r.data);

// Volume Plans
export const getVolumePlans = (date: string) => api.get(`/api/volume-plans?date=${date}`).then(r => r.data);
export const saveVolumePlans = (date: string, plans: { volume_type: string; time_slot_start: string; volume: number }[]) => api.post('/api/volume-plans/bulk', { plan_date: date, plans }).then(r => r.data);

// Volume Expansions
export const getVolumeExpansions = (date: string) => api.get(`/api/volume-expansions?date=${date}`).then(r => r.data);
export const runVolumeExpansion = (date: string) => api.post('/api/volume-expansions/expand', { plan_date: date }).then(r => r.data);

// Optimization
export const runOptimization = (date: string) => api.post('/api/optimization/run', { plan_date: date }).then(r => r.data);
export const getOptimizationResults = (date: string) => api.get(`/api/optimization/results?date=${date}`).then(r => r.data);
export const getOptimizationAssignments = (resultId: string) => api.get(`/api/optimization/results/${resultId}/assignments`).then(r => r.data);
export const selectOptimizationResult = (resultId: string) => api.post(`/api/optimization/results/${resultId}/select`).then(r => r.data);

// Shifts
export const getShifts = (date: string) => api.get(`/api/shifts?date=${date}`).then(r => r.data);
export const generateShifts = (date: string) => api.post('/api/shifts/generate', { plan_date: date }).then(r => r.data);
export const exportShifts = (date: string) => api.get(`/api/shifts/${date}/export`, { responseType: 'blob' }).then(r => r.data);

export default api;
