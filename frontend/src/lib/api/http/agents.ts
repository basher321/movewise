// Partner agents, the agent of a case, and agent commissions (B16). Agents are never deleted.

import type {
  AgentCommission,
  AgentFilters,
  CaseRow,
  CommissionFilters,
  PartnerAgent,
  PartnerAgentInput,
} from "../types";
import { get, post, put } from "./client";

export const listAgents = (filters: AgentFilters = {}) =>
  get<PartnerAgent[]>("/admin/agents", { q: filters.q, section: filters.section, active: filters.active });
export const createAgent = (input: PartnerAgentInput) => post<PartnerAgent>("/admin/agents", input);
export const updateAgent = (id: string, input: PartnerAgentInput) => put<PartnerAgent>("/admin/agents/" + id, input);
export const setApplicationAgent = (applicationId: string, agentId: string | null) =>
  put<CaseRow>(`/admin/applications/${applicationId}/agent`, { agent_id: agentId });
export const listCommissions = (filters: CommissionFilters = {}) =>
  get<AgentCommission[]>("/admin/agents/commissions", { agent_id: filters.agent_id, status: filters.status, module: filters.module });
export const setCommission = (id: string, amountPoisha: number, note: string) =>
  put<AgentCommission>("/admin/agents/commissions/" + id, { amount_poisha: amountPoisha, note });
export const payCommission = (id: string, payReference: string) =>
  post<AgentCommission>(`/admin/agents/commissions/${id}/pay`, { pay_reference: payReference });
export const cancelCommission = (id: string, note: string) =>
  post<AgentCommission>(`/admin/agents/commissions/${id}/cancel`, { note });
