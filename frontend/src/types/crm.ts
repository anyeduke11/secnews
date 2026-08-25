/**
 * types/crm — CRM 业绩座舱 API 契约类型 (与 backend crm_* repo/api 对齐)
 */

export interface CrmCustomer {
  id: number;
  name: string;
  industry: string;
  level: string;
  status: string;
  region: string;
  owner: string;
  contact_name: string;
  contact_phone: string;
  email: string;
  contract_start_date: string | null;
  contract_end_date: string | null;
  contract_amount: number;
  nps_score: number | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface CrmOpportunityEvent {
  id: number;
  opportunity_id: number;
  from_stage: string | null;
  to_stage: string;
  note: string;
  created_at: string;
}

export interface CrmOpportunity {
  id: number;
  customer_id: number;
  name: string;
  service_type: string;
  stage: string;
  amount: number;
  cost: number;
  owner: string;
  expected_close_date: string | null;
  description: string;
  won_at: string | null;
  lost_reason: string;
  created_at: string;
  updated_at: string;
  events?: CrmOpportunityEvent[];
}

export interface CrmListResponse<T> {
  items: T[];
  total: number;
  limit: number;
}

/** GET /api/crm/stats — 8 KPI + 3 图表 (口径 docs/COCKPIT_PRD.md §3) */
export interface CockpitStats {
  kpi: {
    annual_revenue: number;
    gross_margin: number | null;
    customers_total: number;
    repeat_rate: number | null;
    in_pipeline: number;
    win_rate: number | null;
    avg_deal_size: number | null;
    nps: number | null;
  };
  charts: {
    monthly_revenue: { month: string; revenue: number }[];
    region_distribution: { region: string; amount: number }[];
    funnel: { stage: string; count: number; amount: number }[];
  };
}

/** GET /api/crm/meta — 表单枚举选项 */
export interface CrmMeta {
  stages: string[];
  levels: string[];
  statuses: string[];
  industries: string[];
}
