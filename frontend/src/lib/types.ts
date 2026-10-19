export type TicketStatus =
  | "OPEN"
  | "WAITING_FOR_CLIENT"
  | "SNOOZED_TONIGHT"
  | "NEEDS_CORRECTION"
  | "NEEDS_CLERK_REVIEW"
  | "RESOLVED"
  | "ESCALATED";

export type TicketPriority = "NORMAL" | "HIGH" | "URGENT_DEADLINE";
export type TemplateCategory = "MISSING_INVOICE" | "MISSING_DETAIL" | "UNIDENTIFIED_CHARGE" | "TAX_READY" | "MONTHLY_FOLDER";
export type MessageType = "TEMPLATE" | "TEXT" | "BUTTON_REPLY" | "IMAGE_UPLOAD" | "AUTO_REMINDER" | "OCR_FEEDBACK";
export type DeliveryStatus = "SENT" | "DELIVERED" | "READ" | "FAILED";
export type PaymentStatus = "SENT" | "VIEWED" | "CONFIRMED_PAID" | "QUESTION_ASKED";

export type UserRole = "MANAGER" | "WORKER";
export type ReportingFrequency = "MONTHLY" | "BIMONTHLY";

export interface User {
  id: number;
  full_name: string;
  /** e.g. "פקיד הנה״ח" — shown under the name */
  job_title: string;
  email: string;
  role: UserRole;
  avatar_initials: string;
  is_active: boolean;
  created_at: string;
}

export interface Client {
  id: number;
  full_name: string;
  company_name: string;
  tax_id: string;
  whatsapp_phone: string;
  reporting_frequency: ReportingFrequency;
  assigned_worker_id: number | null;
  assigned_worker_name: string | null;
  notes: string;
  is_active: boolean;
  created_at: string;
  open_ticket_count: number;
  days_to_deadline: number;
  /** dd/mm/yyyy — always the 26th of a reporting month */
  next_deadline: string;
  last_message_at: string | null;
  last_message_preview: string | null;
}

export type ClientInput = Pick<
  Client,
  "full_name" | "company_name" | "tax_id" | "whatsapp_phone" | "reporting_frequency" | "assigned_worker_id" | "notes" | "is_active"
>;

export interface TemplateButton {
  id: string;
  action: string;
  he: string;
}

export interface Template {
  id: number;
  slug: string;
  category: TemplateCategory;
  name_he: string;
  body_he: string;
  buttons_json: TemplateButton[];
  requires_media_reply: boolean;
  is_system: boolean;
  updated_at: string;
  variables: string[];
  required_variables: string[];
}

export interface RenderedButton {
  id: string;
  title: string;
  action: string;
}

export interface Message {
  id: number;
  ticket_id: number | null;
  client_id: number;
  direction: "OUTBOUND" | "INBOUND";
  sender_name: string;
  /** true for bot / template / reminder / Vision AI messages; false for a worker's manual message */
  is_automated: boolean;
  /** the worker who wrote a manual message */
  sender_user_id: number | null;
  message_type: MessageType;
  content_text: string;
  buttons_json: RenderedButton[] | null;
  media_url: string | null;
  delivery_status: DeliveryStatus;
  error_text: string | null;
  created_at: string;
}

export interface OcrChecks {
  clarity: boolean | null;
  document_type: boolean | null;
  supplier_match: boolean | null;
  math_integrity: boolean | null;
  tax_id: boolean | null;
  allocation_number: boolean | null;
}

export interface OcrResult {
  is_valid: boolean | null;
  status: "PASSED" | "FAILED" | "MANUAL_REVIEW";
  is_blurry: boolean;
  blur_score: number | null;
  has_tax_invoice_header: boolean;
  document_title: string | null;
  detected_supplier: string | null;
  detected_invoice_num: string | null;
  invoice_number: string | null;
  supplier_name: string | null;
  business_id: string | null;
  allocation_number: string | null;
  allocation_required: boolean | null;
  allocation_threshold: number | null;
  vat_rate_applied: number | null;
  invoice_date: string | null;
  net_amount: number | null;
  vat_amount: number | null;
  total_amount: number | null;
  math_valid: boolean | null;
  vat_rate_ok: boolean | null;
  supplier_match: boolean | null;
  supplier_match_score: number | null;
  expected_supplier: string | null;
  confidence_score: number;
  checks: OcrChecks;
  rejection_codes: string[];
  warnings: string[];
  rejection_reason: string | null;
  rejection_reason_he: string | null;
  manual_review_required: boolean;
  provider: string;
  simulated: boolean;
  provider_note: string;
  clerk_edited?: boolean;
  approved?: boolean;
  approved_by?: string | null;
}

export interface Ticket {
  id: number;
  ticket_ref: string;
  client_id: number;
  client_name: string;
  company_name: string;
  client_phone: string;
  worker_id: number | null;
  worker_name: string | null;
  template_id: number;
  template_slug: string;
  template_name: string;
  category: TemplateCategory;
  requires_media_reply: boolean;
  status: TicketStatus;
  priority: TicketPriority;
  context_variables_json: Record<string, string | number | boolean | null>;
  reminder_count: number;
  max_reminders: number;
  last_contacted_at: string | null;
  next_reminder_at: string | null;
  resolved_at: string | null;
  media_file_path: string | null;
  ocr_validation_json: OcrResult | null;
  resolution_note: string;
  created_at: string;
  updated_at: string;
}

export interface TicketDetail extends Ticket {
  messages: Message[];
}

export interface QuickSendResponse {
  ticket: Ticket;
  message: Message;
  rendered_text: string;
  buttons: RenderedButton[];
  direction: "rtl" | "ltr";
  elapsed_ms: number;
}

export interface InboundResult {
  ok: boolean;
  ticket: Ticket | null;
  action: string | null;
  reply: string | null;
  ocr: OcrResult | null;
  validation: { field: "allocation_number" | "tax_id"; valid: boolean; value: string } | null;
  /** no open request was waiting for this input: saved to the chat history only, no bot reply */
  unsolicited: boolean;
  elapsed_ms: number | null;
}

export interface Kpis {
  active_waiting: number;
  auto_reminders_this_month: number;
  needs_clerk_review: number;
  resolved_this_week: number;
  escalated: number;
  needs_correction: number;
  estimated_hours_saved: number;
  hours_saved_basis: string;
}

export interface SchedulerAction {
  kind: "FRIENDLY_REMINDER" | "URGENT_DEADLINE_WARNING" | "URGENT_GROUPED" | "ESCALATED" | "SNOOZE_PING";
  ticket_id: number;
  ticket_ref: string;
  client_id: number;
  client_name: string;
  status: TicketStatus;
  priority: TicketPriority;
  reminder_count: number;
  message: string;
}

export interface SchedulerResult {
  shifted_tickets: number | null;
  actions: SchedulerAction[];
  summary: Record<string, number>;
}

export interface AppSettings {
  id: number;
  firm_name: string;
  vat_rate: number;
  allocation_number_threshold_nis: number;
  reminder_interval_hours: number;
  max_reminders: number;
  /** Fixed by law: VAT reports are due on the 26th (read-only) */
  vat_deadline_day: number;
  auto_approve_verified: boolean;
  updated_at: string;
  updated_by_user_id: number | null;
  updated_by_name: string | null;
  vision_provider: string;
  whatsapp_live: boolean;
  timezone: string;
  urgent_deadline_days: number;
  scheduler: { enabled: boolean; running: boolean; interval_seconds: number; next_run_at: string | null };
}

export type EditableSettings = Pick<
  AppSettings,
  | "firm_name"
  | "vat_rate"
  | "allocation_number_threshold_nis"
  | "reminder_interval_hours"
  | "max_reminders"
  | "auto_approve_verified"
>;

export interface CampaignStats {
  total: number;
  sent: number;
  pending: number;
  viewed: number;
  confirmed_paid: number;
  requested_call: number;
  total_due: number;
  confirmed_amount: number;
}

export interface Recipient {
  id: number;
  client_id: number;
  client_name: string;
  ticket_id: number | null;
  ticket_ref: string | null;
  ticket_status: TicketStatus | null;
  vat_amount: number;
  income_tax_advance: number;
  national_insurance: number;
  total_due: number;
  due_date: string;
  payment_status: PaymentStatus;
  updated_at: string;
}

export interface Campaign {
  id: number;
  title: string;
  tax_period: string;
  total_clients: number;
  confirmed_count: number;
  pending_count: number;
  created_at: string;
  stats: CampaignStats;
}

export interface CampaignDetail extends Campaign {
  recipients: Recipient[];
}

export interface BulkUploadResult {
  campaign: CampaignDetail;
  errors: string[];
  created_clients: number;
  sent: number;
}

export interface ServerEvent {
  type: "hello" | "message" | "ticket" | "campaign" | "scheduler" | "client" | "template" | "settings" | "users" | "activity";
  client_id?: number;
  ticket_id?: number | null;
  campaign_id?: number;
  status?: TicketStatus;
  count?: number;
}

export type LoginUser = Pick<User, "id" | "full_name" | "job_title" | "role" | "avatar_initials" | "is_active">;

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: User;
}

export interface ActivityEntry {
  id: number;
  created_at: string;
  user_id: number | null;
  user_name: string | null;
  user_role: UserRole | null;
  action: string;
  action_label: string;
  description: string;
  entity_type: string | null;
  entity_id: number | null;
  details: Record<string, unknown> | null;
  ip_address: string;
}

export interface ActivityPage {
  total: number;
  items: ActivityEntry[];
  actions: Record<string, string>;
}
