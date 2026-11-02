
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  
  "graphql_public": {
          Tables: {
            [_ in never]: never
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "graphql":
{ Args: { "extensions"?: Json,"operationName"?: string,"query"?: string,"variables"?: Json }; Returns: Json
                           }
          }
          Enums: {
            [_ in never]: never
          }
          CompositeTypes: {
            [_ in never]: never
          }
        },"public": {
          Tables: {
            "audit_log": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_role": string | null,"after": Json | null,"before": Json | null,"department_id": string | null,"entity": string,"entity_id": string | null,"id": number,"ip_hash": string | null,"occurred_at": string,"request_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_role"?: string | null,"after"?: Json | null,"before"?: Json | null,"department_id"?: string | null,"entity": string,"entity_id"?: string | null,"id"?: never,"ip_hash"?: string | null,"occurred_at"?: string,"request_id"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_role"?: string | null,"after"?: Json | null,"before"?: Json | null,"department_id"?: string | null,"entity"?: string,"entity_id"?: string | null,"id"?: never,"ip_hash"?: string | null,"occurred_at"?: string,"request_id"?: string | null
                  }
                  Relationships: [
                    
                  ]
                },"datasets": {
                  Row: {
                    "config_hash": string | null,"content_hash": string,"created_at": string,"created_by": string | null,"department_id": string,"id": string,"import_job_id": string | null,"name": string,"row_count": number,"seed": number | null,"source": string
                  }
                  ComputedFields: never
                  Insert: {
                    "config_hash"?: string | null,"content_hash": string,"created_at"?: string,"created_by"?: string | null,"department_id": string,"id"?: string,"import_job_id"?: string | null,"name": string,"row_count": number,"seed"?: number | null,"source": string
                  }
                  Update: {
                    "config_hash"?: string | null,"content_hash"?: string,"created_at"?: string,"created_by"?: string | null,"department_id"?: string,"id"?: string,"import_job_id"?: string | null,"name"?: string,"row_count"?: number,"seed"?: number | null,"source"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "datasets_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "datasets_import_job_id_fkey"
      columns: ["import_job_id"]
isOneToOne: false
      referencedRelation: "import_jobs"
      referencedColumns: ["id"]
    }
                  ]
                },"departments": {
                  Row: {
                    "created_at": string,"facility_id": string,"id": string,"name": string,"settings": NonNullable<Json>,"slug": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"facility_id": string,"id"?: string,"name": string,"settings"?: NonNullable<Json>,"slug": string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"facility_id"?: string,"id"?: string,"name"?: string,"settings"?: NonNullable<Json>,"slug"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "departments_facility_id_fkey"
      columns: ["facility_id"]
isOneToOne: false
      referencedRelation: "facilities"
      referencedColumns: ["id"]
    }
                  ]
                },"facilities": {
                  Row: {
                    "created_at": string,"id": string,"name": string,"organization_id": string,"timezone": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"name": string,"organization_id": string,"timezone"?: string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"name"?: string,"organization_id"?: string,"timezone"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "facilities_organization_id_fkey"
      columns: ["organization_id"]
isOneToOne: false
      referencedRelation: "organizations"
      referencedColumns: ["id"]
    }
                  ]
                },"forecast_drivers": {
                  Row: {
                    "contribution_hours": number,"default_text": string,"feature": string,"forecast_id": string,"rank": number,"text_key": string,"text_params": NonNullable<Json>,"value": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "contribution_hours": number,"default_text": string,"feature": string,"forecast_id": string,"rank": number,"text_key": string,"text_params"?: NonNullable<Json>,"value"?: string | null
                  }
                  Update: {
                    "contribution_hours"?: number,"default_text"?: string,"feature"?: string,"forecast_id"?: string,"rank"?: number,"text_key"?: string,"text_params"?: NonNullable<Json>,"value"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "forecast_drivers_forecast_id_fkey"
      columns: ["forecast_id"]
isOneToOne: false
      referencedRelation: "forecasts"
      referencedColumns: ["id"]
    }
                  ]
                },"forecasts": {
                  Row: {
                    "burden_class": string | null,"burden_probs": Json | null,"created_at": string,"created_by": string | null,"department_id": string,"feature_set": string,"id": string,"model_version": string,"ot_p10": number | null,"ot_p50": number | null,"ot_p90": number | null,"plan_id": string | null,"target_date": string,"thresholds": Json | null,"trigger": string
                  }
                  ComputedFields: never
                  Insert: {
                    "burden_class"?: string | null,"burden_probs"?: Json | null,"created_at"?: string,"created_by"?: string | null,"department_id": string,"feature_set": string,"id"?: string,"model_version": string,"ot_p10"?: number | null,"ot_p50"?: number | null,"ot_p90"?: number | null,"plan_id"?: string | null,"target_date": string,"thresholds"?: Json | null,"trigger": string
                  }
                  Update: {
                    "burden_class"?: string | null,"burden_probs"?: Json | null,"created_at"?: string,"created_by"?: string | null,"department_id"?: string,"feature_set"?: string,"id"?: string,"model_version"?: string,"ot_p10"?: number | null,"ot_p50"?: number | null,"ot_p90"?: number | null,"plan_id"?: string | null,"target_date"?: string,"thresholds"?: Json | null,"trigger"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "forecasts_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "forecasts_plan_id_fkey"
      columns: ["plan_id"]
isOneToOne: false
      referencedRelation: "shift_plans"
      referencedColumns: ["id"]
    }
                  ]
                },"idempotency_keys": {
                  Row: {
                    "body_hash": string,"created_at": string,"key": string,"method": string,"path": string,"response": NonNullable<Json>,"status": number,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "body_hash": string,"created_at"?: string,"key": string,"method": string,"path": string,"response": NonNullable<Json>,"status": number,"user_id": string
                  }
                  Update: {
                    "body_hash"?: string,"created_at"?: string,"key"?: string,"method"?: string,"path"?: string,"response"?: NonNullable<Json>,"status"?: number,"user_id"?: string
                  }
                  Relationships: [
                    
                  ]
                },"import_jobs": {
                  Row: {
                    "approved_by": string | null,"content_hash": string,"created_at": string,"created_by": string | null,"department_id": string,"id": string,"mapping": Json | null,"original_filename": string,"parse_report": Json | null,"phi_findings": Json | null,"rows_committed": number | null,"status": string,"storage_path": string | null,"updated_at": string,"validation_report": Json | null
                  }
                  ComputedFields: never
                  Insert: {
                    "approved_by"?: string | null,"content_hash": string,"created_at"?: string,"created_by"?: string | null,"department_id": string,"id"?: string,"mapping"?: Json | null,"original_filename": string,"parse_report"?: Json | null,"phi_findings"?: Json | null,"rows_committed"?: number | null,"status"?: string,"storage_path"?: string | null,"updated_at"?: string,"validation_report"?: Json | null
                  }
                  Update: {
                    "approved_by"?: string | null,"content_hash"?: string,"created_at"?: string,"created_by"?: string | null,"department_id"?: string,"id"?: string,"mapping"?: Json | null,"original_filename"?: string,"parse_report"?: Json | null,"phi_findings"?: Json | null,"rows_committed"?: number | null,"status"?: string,"storage_path"?: string | null,"updated_at"?: string,"validation_report"?: Json | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "import_jobs_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                },"invites": {
                  Row: {
                    "accepted_at": string | null,"created_at": string,"department_id": string,"email": string,"expires_at": string,"id": string,"invited_by": string,"revoked_at": string | null,"role": Database["public"]['Enums']["app_role"]
                  }
                  ComputedFields: never
                  Insert: {
                    "accepted_at"?: string | null,"created_at"?: string,"department_id": string,"email": string,"expires_at"?: string,"id"?: string,"invited_by": string,"revoked_at"?: string | null,"role": Database["public"]['Enums']["app_role"]
                  }
                  Update: {
                    "accepted_at"?: string | null,"created_at"?: string,"department_id"?: string,"email"?: string,"expires_at"?: string,"id"?: string,"invited_by"?: string,"revoked_at"?: string | null,"role"?: Database["public"]['Enums']["app_role"]
                  }
                  Relationships: [
                    {
      foreignKeyName: "invites_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                },"mapping_templates": {
                  Row: {
                    "column_signature": string,"created_at": string,"created_by": string | null,"department_id": string,"id": string,"mapping": NonNullable<Json>
                  }
                  ComputedFields: never
                  Insert: {
                    "column_signature": string,"created_at"?: string,"created_by"?: string | null,"department_id": string,"id"?: string,"mapping": NonNullable<Json>
                  }
                  Update: {
                    "column_signature"?: string,"created_at"?: string,"created_by"?: string | null,"department_id"?: string,"id"?: string,"mapping"?: NonNullable<Json>
                  }
                  Relationships: [
                    {
      foreignKeyName: "mapping_templates_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                },"memberships": {
                  Row: {
                    "created_at": string,"department_id": string,"role": Database["public"]['Enums']["app_role"],"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"department_id": string,"role": Database["public"]['Enums']["app_role"],"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"department_id"?: string,"role"?: Database["public"]['Enums']["app_role"],"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "memberships_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                },"model_versions": {
                  Row: {
                    "activated_at": string | null,"activated_by": string | null,"artifact_path": string,"card": NonNullable<Json>,"code_sha": string | null,"created_at": string,"data_hash": string | null,"feature_set": string,"gates_passed": boolean,"id": string,"metrics": NonNullable<Json>,"status": string,"training_dataset_ids": (string)[],"version": string
                  }
                  ComputedFields: never
                  Insert: {
                    "activated_at"?: string | null,"activated_by"?: string | null,"artifact_path": string,"card": NonNullable<Json>,"code_sha"?: string | null,"created_at"?: string,"data_hash"?: string | null,"feature_set": string,"gates_passed"?: boolean,"id"?: string,"metrics": NonNullable<Json>,"status"?: string,"training_dataset_ids": (string)[],"version": string
                  }
                  Update: {
                    "activated_at"?: string | null,"activated_by"?: string | null,"artifact_path"?: string,"card"?: NonNullable<Json>,"code_sha"?: string | null,"created_at"?: string,"data_hash"?: string | null,"feature_set"?: string,"gates_passed"?: boolean,"id"?: string,"metrics"?: NonNullable<Json>,"status"?: string,"training_dataset_ids"?: (string)[],"version"?: string
                  }
                  Relationships: [
                    
                  ]
                },"organizations": {
                  Row: {
                    "allowed_email_domains": (string)[],"created_at": string,"id": string,"name": string
                  }
                  ComputedFields: never
                  Insert: {
                    "allowed_email_domains"?: (string)[],"created_at"?: string,"id"?: string,"name": string
                  }
                  Update: {
                    "allowed_email_domains"?: (string)[],"created_at"?: string,"id"?: string,"name"?: string
                  }
                  Relationships: [
                    
                  ]
                },"profiles": {
                  Row: {
                    "created_at": string,"display_name": string | null,"locale": string,"theme": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"display_name"?: string | null,"locale"?: string,"theme"?: string,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"display_name"?: string | null,"locale"?: string,"theme"?: string,"user_id"?: string
                  }
                  Relationships: [
                    
                  ]
                },"scenarios": {
                  Row: {
                    "applied": boolean,"applied_at": string | null,"applied_by": string | null,"applied_option_id": string | null,"created_at": string,"created_by": string | null,"department_id": string,"forecast_id": string | null,"id": string,"model_version": string,"request": NonNullable<Json>,"result": NonNullable<Json>,"target_date": string
                  }
                  ComputedFields: never
                  Insert: {
                    "applied"?: boolean,"applied_at"?: string | null,"applied_by"?: string | null,"applied_option_id"?: string | null,"created_at"?: string,"created_by"?: string | null,"department_id": string,"forecast_id"?: string | null,"id"?: string,"model_version": string,"request": NonNullable<Json>,"result": NonNullable<Json>,"target_date": string
                  }
                  Update: {
                    "applied"?: boolean,"applied_at"?: string | null,"applied_by"?: string | null,"applied_option_id"?: string | null,"created_at"?: string,"created_by"?: string | null,"department_id"?: string,"forecast_id"?: string | null,"id"?: string,"model_version"?: string,"request"?: NonNullable<Json>,"result"?: NonNullable<Json>,"target_date"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "scenarios_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "scenarios_forecast_id_fkey"
      columns: ["forecast_id"]
isOneToOne: false
      referencedRelation: "forecasts"
      referencedColumns: ["id"]
    }
                  ]
                },"shift_actuals": {
                  Row: {
                    "approved_at": string | null,"approved_by": string | null,"created_at": string,"created_by": string | null,"created_by_role": string | null,"dataset_id": string | null,"department_id": string,"emergency_intake_patients": number | null,"equipment_downtime_minutes": number | null,"id": string,"notes": string | null,"ot_labor_hours": number,"reopen_reason": string | null,"reopened_at": string | null,"reopened_by": string | null,"returned_unused_estimate": number | null,"shift_date": string,"source": string,"status": string,"submitted_by": string | null,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "approved_at"?: string | null,"approved_by"?: string | null,"created_at"?: string,"created_by"?: string | null,"created_by_role"?: string | null,"dataset_id"?: string | null,"department_id": string,"emergency_intake_patients"?: number | null,"equipment_downtime_minutes"?: number | null,"id"?: string,"notes"?: string | null,"ot_labor_hours": number,"reopen_reason"?: string | null,"reopened_at"?: string | null,"reopened_by"?: string | null,"returned_unused_estimate"?: number | null,"shift_date": string,"source": string,"status"?: string,"submitted_by"?: string | null,"updated_at"?: string
                  }
                  Update: {
                    "approved_at"?: string | null,"approved_by"?: string | null,"created_at"?: string,"created_by"?: string | null,"created_by_role"?: string | null,"dataset_id"?: string | null,"department_id"?: string,"emergency_intake_patients"?: number | null,"equipment_downtime_minutes"?: number | null,"id"?: string,"notes"?: string | null,"ot_labor_hours"?: number,"reopen_reason"?: string | null,"reopened_at"?: string | null,"reopened_by"?: string | null,"returned_unused_estimate"?: number | null,"shift_date"?: string,"source"?: string,"status"?: string,"submitted_by"?: string | null,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "shift_actuals_dataset_id_fkey"
      columns: ["dataset_id"]
isOneToOne: false
      referencedRelation: "datasets"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "shift_actuals_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                },"shift_plans": {
                  Row: {
                    "academic_event": string | null,"academic_event__missing": boolean,"aft_11_staff": number | null,"aft_11_staff__missing": boolean,"aft_13_staff": number | null,"aft_13_staff__missing": boolean,"aft_15_staff": number | null,"aft_15_staff__missing": boolean,"carryover_backlog_estimate": number | null,"carryover_backlog_estimate__missing": boolean,"created_at": string,"created_by": string | null,"dataset_id": string | null,"department_id": string,"id": string,"is_holiday": boolean | null,"is_holiday__missing": boolean,"mf_cases": number | null,"mf_cases__missing": boolean,"morning_staff_present": number,"ot_available_staff": number | null,"ot_available_staff__missing": boolean,"outside_support_staff": number | null,"outside_support_staff__missing": boolean,"plan_date": string,"regular_patients": number,"source": string,"status": string,"sterilizers_up": number | null,"sterilizers_up__missing": boolean,"student_clinic_sessions": number | null,"student_clinic_sessions__missing": boolean,"updated_at": string,"updated_by": string | null,"washers_up": number | null,"washers_up__missing": boolean
                  }
                  ComputedFields: never
                  Insert: {
                    "academic_event"?: string | null,"academic_event__missing"?: boolean,"aft_11_staff"?: number | null,"aft_11_staff__missing"?: boolean,"aft_13_staff"?: number | null,"aft_13_staff__missing"?: boolean,"aft_15_staff"?: number | null,"aft_15_staff__missing"?: boolean,"carryover_backlog_estimate"?: number | null,"carryover_backlog_estimate__missing"?: boolean,"created_at"?: string,"created_by"?: string | null,"dataset_id"?: string | null,"department_id": string,"id"?: string,"is_holiday"?: boolean | null,"is_holiday__missing"?: boolean,"mf_cases"?: number | null,"mf_cases__missing"?: boolean,"morning_staff_present": number,"ot_available_staff"?: number | null,"ot_available_staff__missing"?: boolean,"outside_support_staff"?: number | null,"outside_support_staff__missing"?: boolean,"plan_date": string,"regular_patients": number,"source": string,"status"?: string,"sterilizers_up"?: number | null,"sterilizers_up__missing"?: boolean,"student_clinic_sessions"?: number | null,"student_clinic_sessions__missing"?: boolean,"updated_at"?: string,"updated_by"?: string | null,"washers_up"?: number | null,"washers_up__missing"?: boolean
                  }
                  Update: {
                    "academic_event"?: string | null,"academic_event__missing"?: boolean,"aft_11_staff"?: number | null,"aft_11_staff__missing"?: boolean,"aft_13_staff"?: number | null,"aft_13_staff__missing"?: boolean,"aft_15_staff"?: number | null,"aft_15_staff__missing"?: boolean,"carryover_backlog_estimate"?: number | null,"carryover_backlog_estimate__missing"?: boolean,"created_at"?: string,"created_by"?: string | null,"dataset_id"?: string | null,"department_id"?: string,"id"?: string,"is_holiday"?: boolean | null,"is_holiday__missing"?: boolean,"mf_cases"?: number | null,"mf_cases__missing"?: boolean,"morning_staff_present"?: number,"ot_available_staff"?: number | null,"ot_available_staff__missing"?: boolean,"outside_support_staff"?: number | null,"outside_support_staff__missing"?: boolean,"plan_date"?: string,"regular_patients"?: number,"source"?: string,"status"?: string,"sterilizers_up"?: number | null,"sterilizers_up__missing"?: boolean,"student_clinic_sessions"?: number | null,"student_clinic_sessions__missing"?: boolean,"updated_at"?: string,"updated_by"?: string | null,"washers_up"?: number | null,"washers_up__missing"?: boolean
                  }
                  Relationships: [
                    {
      foreignKeyName: "shift_plans_dataset_id_fkey"
      columns: ["dataset_id"]
isOneToOne: false
      referencedRelation: "datasets"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "shift_plans_department_id_fkey"
      columns: ["department_id"]
isOneToOne: false
      referencedRelation: "departments"
      referencedColumns: ["id"]
    }
                  ]
                }
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "accept_pending_invites":
{ Args: Record<PropertyKey, never>; Returns: number
                           },
"activate_model_version":
{ Args: { "p_actor": string,"p_version": string }; Returns: {
              "activated_at": string | null,
"activated_by": string | null,
"artifact_path": string,
"card": NonNullable<Json>,
"code_sha": string | null,
"created_at": string,
"data_hash": string | null,
"feature_set": string,
"gates_passed": boolean,
"id": string,
"metrics": NonNullable<Json>,
"status": string,
"training_dataset_ids": (string)[],
"version": string
            }
                          SetofOptions: {
        from: "*"
        to: "model_versions"
        isOneToOne: true
        isSetofReturn: false
      } },
"has_any_role":
{ Args: { "roles": (Database["public"]['Enums']["app_role"])[] }; Returns: boolean
                           },
"has_role":
{ Args: { "dept": string,"roles": (Database["public"]['Enums']["app_role"])[] }; Returns: boolean
                           },
"is_aal2":
{ Args: Record<PropertyKey, never>; Returns: boolean
                           },
"is_member":
{ Args: { "dept": string }; Returns: boolean
                           },
"is_platform_admin":
{ Args: Record<PropertyKey, never>; Returns: boolean
                           },
"purge_idempotency_keys":
{ Args: Record<PropertyKey, never>; Returns: number
                           },
"rollback_model_version":
{ Args: { "p_actor": string,"p_feature_set": string }; Returns: {
              "activated_at": string | null,
"activated_by": string | null,
"artifact_path": string,
"card": NonNullable<Json>,
"code_sha": string | null,
"created_at": string,
"data_hash": string | null,
"feature_set": string,
"gates_passed": boolean,
"id": string,
"metrics": NonNullable<Json>,
"status": string,
"training_dataset_ids": (string)[],
"version": string
            }
                          SetofOptions: {
        from: "*"
        to: "model_versions"
        isOneToOne: true
        isSetofReturn: false
      } },
"session_age_seconds":
{ Args: Record<PropertyKey, never>; Returns: number
                           }
          }
          Enums: {
            "app_role": "technician"|"supervisor"|"dept_admin"|"data_steward"|"platform_admin"
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "graphql_public": {
          Enums: {
            
          }
        },"public": {
          Enums: {
            "app_role": ["technician", "supervisor", "dept_admin", "data_steward", "platform_admin"]
          }
        }
} as const
