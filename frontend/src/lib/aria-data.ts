export const RUN_ID = "run_8f3c1a90b27e"
export const DATA_FILE_ID = "file_h2026_5482"
export const AUTO_RUN_ID = "arun_b71d9e2c"

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
export type Risk = "low" | "medium" | "high" | "critical"
export type RunStatus = "completed" | "running" | "pending" | "failed" | "parsing"
export type UserStatus = "active" | "pending" | "rejected"
export type Role = "admin" | "api_analyst" | "business_user" | "approver" | "automation_operator" | "auditor"

export interface Endpoint {
  method: Method; path: string; canonical: string; domain: string
  action: string; auth: boolean; status: number[]; samples: number
  confidence: number; risk: Risk; tags: string[]
}
export interface WorkflowStep {
  order: number; method: Method; path: string; canonical: string
  action: string; risk: Risk; auth: boolean; depends: number[]
}
export interface Workflow {
  id: string; name: string; domain: string; confidence: number
  description: string; steps: WorkflowStep[]
  hasOriginal: boolean
  isManual: boolean  // [F1] true if created_by === "user"
}
export interface CsvRow {
  idx: number; first: string; last: string; email: string; dept: string
  position: string; start: string; salary: string; iban: string; contract: string
}
export interface MappingRow {
  src: string; dst: string | null; confidence: number
  kind: "exact" | "synonym" | "rules" | "missing"
  approved: boolean; required: boolean; pii?: boolean; resolveRef?: boolean
}
export interface ValidationError { row: number; field: string; code: string; message: string }
export interface Batch { batch: number; start: number; end: number; status: RunStatus; success: number; failed: number }
export interface RunOption { id: string; label: string; short?: string }
export interface AutoRunOption { id: string; label: string }
export interface RecentRun { id: string; name: string; source: string; status: RunStatus; endpoints: number; created: string; duration: string }
export interface RecentAutomation { id: string; workflow: string; rows: number; success: number; failed: number; status: RunStatus; started: string; dryRun: boolean }
export interface Approval { id: string; run: string; workflow: string; rows: number; invalid: number; risk: Risk; requestedBy: string; requestedAt: string; methods: Method[]; targets: string[] }
export interface User { name: string; email: string; role: Role; status: UserStatus }
export interface RoleInfo { label: string; swatch: string; description: string }

export const ENDPOINTS: Endpoint[] = [
  { method:"POST",   path:"/api/v1/auth/login",                         canonical:"auth.login",             domain:"auth",    action:"authenticate", auth:false, status:[200,401,422], samples:14, confidence:0.98, risk:"low",      tags:["auth"] },
  { method:"POST",   path:"/api/v1/auth/refresh",                       canonical:"auth.refresh_token",     domain:"auth",    action:"refresh",      auth:true,  status:[200,401],     samples:8,  confidence:0.95, risk:"low",      tags:["auth"] },
  { method:"GET",    path:"/api/v1/employees",                          canonical:"hr.employees.list",      domain:"hr",      action:"list",         auth:true,  status:[200],         samples:31, confidence:0.99, risk:"low",      tags:["hr","read"] },
  { method:"POST",   path:"/api/v1/employees",                          canonical:"hr.employees.create",    domain:"hr",      action:"create",       auth:true,  status:[201,400,422], samples:24, confidence:0.97, risk:"medium",   tags:["hr","write"] },
  { method:"GET",    path:"/api/v1/employees/{employee_id}",            canonical:"hr.employees.get",       domain:"hr",      action:"read",         auth:true,  status:[200,404],     samples:18, confidence:0.99, risk:"low",      tags:["hr","read"] },
  { method:"PATCH",  path:"/api/v1/employees/{employee_id}",            canonical:"hr.employees.update",    domain:"hr",      action:"update",       auth:true,  status:[200,404,422], samples:12, confidence:0.94, risk:"medium",   tags:["hr","write"] },
  { method:"POST",   path:"/api/v1/employees/{employee_id}/contracts",  canonical:"hr.contracts.create",    domain:"hr",      action:"create",       auth:true,  status:[201,422],     samples:21, confidence:0.96, risk:"high",     tags:["hr","write"] },
  { method:"GET",    path:"/api/v1/departments",                        canonical:"hr.departments.list",    domain:"hr",      action:"list",         auth:true,  status:[200],         samples:9,  confidence:0.99, risk:"low",      tags:["hr","ref"] },
  { method:"GET",    path:"/api/v1/positions",                          canonical:"hr.positions.list",      domain:"hr",      action:"list",         auth:true,  status:[200],         samples:6,  confidence:0.99, risk:"low",      tags:["hr","ref"] },
  { method:"POST",   path:"/api/v1/payroll/accounts",                   canonical:"payroll.account.create", domain:"payroll", action:"create",       auth:true,  status:[201,422],     samples:11, confidence:0.93, risk:"high",     tags:["payroll","write"] },
  { method:"PUT",    path:"/api/v1/payroll/accounts/{account_id}/iban", canonical:"payroll.iban.update",    domain:"payroll", action:"update",       auth:true,  status:[200,422],     samples:7,  confidence:0.88, risk:"critical", tags:["payroll","pii"] },
  { method:"GET",    path:"/api/v1/payroll/accounts/{account_id}",      canonical:"payroll.account.get",    domain:"payroll", action:"read",         auth:true,  status:[200,404],     samples:5,  confidence:0.96, risk:"medium",   tags:["payroll","read"] },
  { method:"POST",   path:"/api/v1/access/badges",                      canonical:"access.badge.issue",     domain:"access",  action:"create",       auth:true,  status:[201,409],     samples:9,  confidence:0.92, risk:"medium",   tags:["access","write"] },
  { method:"DELETE", path:"/api/v1/access/badges/{badge_id}",           canonical:"access.badge.revoke",    domain:"access",  action:"delete",       auth:true,  status:[204,404],     samples:3,  confidence:0.90, risk:"high",     tags:["access","delete"] },
  { method:"POST",   path:"/api/v1/notifications/welcome",              canonical:"notify.welcome.send",    domain:"notify",  action:"create",       auth:true,  status:[202],         samples:13, confidence:0.91, risk:"low",      tags:["notify"] },
]

export const CSV_ROWS: CsvRow[] = [
  { idx:1, first:"Amelia",   last:"Okonkwo",  email:"amelia.okonkwo@northwind.io",  dept:"Engineering", position:"Senior Engineer", start:"2026-06-01", salary:"€68,000", iban:"DE89 3704 0044…", contract:"CDI" },
  { idx:2, first:"Benoît",   last:"Lemaire",  email:"benoit.lemaire@northwind.io",  dept:"Engineering", position:"Staff Engineer",  start:"2026-06-01", salary:"€84,500", iban:"FR76 3000 6000…", contract:"CDI" },
  { idx:3, first:"Chiamaka", last:"Eze",      email:"chiamaka.eze@northwind.io",    dept:"Product",     position:"Product Manager", start:"2026-06-08", salary:"€71,200", iban:"FR76 3000 6001…", contract:"CDI" },
  { idx:4, first:"Daniela",  last:"Rossi",    email:"daniela.rossi@northwind.io",   dept:"Design",      position:"Lead Designer",   start:"2026-06-08", salary:"€69,800", iban:"IT60 X054 2811…", contract:"CDI" },
  { idx:5, first:"Eitan",    last:"Goldberg", email:"eitan.goldberg@northwind.io",  dept:"Data",        position:"Data Engineer",   start:"2026-06-15", salary:"€62,000", iban:"FR76 3000 6002…", contract:"CDD" },
  { idx:6, first:"Fatou",    last:"Diop",     email:"fatou.diop",                   dept:"Support",     position:"Customer Lead",   start:"2026-06-15", salary:"€48,000", iban:"FR76 3000 6003…", contract:"CDI" },
  { idx:7, first:"Giulia",   last:"Conti",    email:"giulia.conti@northwind.io",    dept:"Marketing",   position:"Growth Lead",     start:"",           salary:"€58,500", iban:"FR76 3000 6004…", contract:"CDI" },
  { idx:8, first:"Haruki",   last:"Tanaka",   email:"haruki.tanaka@northwind.io",   dept:"Engineering", position:"SRE",             start:"2026-06-22", salary:"€72,100", iban:"FR76 3000 6005…", contract:"CDI" },
]

export const MAPPING: MappingRow[] = [
  { src:"first_name",    dst:"firstName",          confidence:0.98, kind:"exact",   approved:true,  required:true },
  { src:"last_name",     dst:"lastName",           confidence:0.98, kind:"exact",   approved:true,  required:true },
  { src:"email",         dst:"contactEmail",       confidence:0.91, kind:"synonym", approved:true,  required:true },
  { src:"department",    dst:"departmentRef",      confidence:0.86, kind:"rules",   approved:true,  required:true, resolveRef:true },
  { src:"position",      dst:"positionRef",        confidence:0.78, kind:"rules",   approved:true,  required:true, resolveRef:true },
  { src:"start_date",    dst:"contract.startDate", confidence:0.95, kind:"exact",   approved:true,  required:true },
  { src:"salary_eur",    dst:"contract.salary",    confidence:0.81, kind:"rules",   approved:true,  required:true },
  { src:"contract_type", dst:"contract.type",      confidence:0.93, kind:"synonym", approved:true,  required:true },
  { src:"iban",          dst:"payroll.iban",       confidence:0.88, kind:"synonym", approved:true,  required:true, pii:true },
  { src:"birth_date",    dst:null,                 confidence:0.0,  kind:"missing", approved:false, required:false, pii:true },
  { src:"manager_email", dst:null,                 confidence:0.0,  kind:"missing", approved:false, required:false },
]

export const VALIDATION_ERRORS: ValidationError[] = [
  { row:6,   field:"email",         code:"INVALID_EMAIL",          message:"Missing @ in 'fatou.diop'" },
  { row:7,   field:"start_date",    code:"MISSING_REQUIRED_FIELD", message:"start_date is required" },
  { row:14,  field:"iban",          code:"INVALID_IBAN",           message:"Checksum failed" },
  { row:42,  field:"contract_type", code:"INVALID_CONTRACT_TYPE",  message:"Got 'PERM', expected CDI/CDD/STAGE" },
  { row:58,  field:"salary_eur",    code:"INVALID_REQUIRED_FIELD", message:"Salary below department minimum (€32,000)" },
  { row:91,  field:"email",         code:"INVALID_EMAIL",          message:"Domain 'gmial.com' not in allowlist" },
  { row:104, field:"start_date",    code:"MISSING_REQUIRED_FIELD", message:"start_date is required" },
  { row:117, field:"iban",          code:"INVALID_IBAN",           message:"Country code 'XX' is unknown" },
  { row:145, field:"manager_email", code:"INVALID_EMAIL",          message:"User not found in directory" },
  { row:201, field:"contract_type", code:"INVALID_CONTRACT_TYPE",  message:"Got 'INTERN', expected CDI/CDD/STAGE" },
  { row:233, field:"department",    code:"REF_NOT_FOUND",          message:"Department 'R&D Labs' not found" },
  { row:280, field:"position",      code:"REF_NOT_FOUND",          message:"Position 'Chief Vibes Officer' not found" },
  { row:312, field:"email",         code:"INVALID_EMAIL",          message:"Duplicate email — already at row 218" },
  { row:418, field:"salary_eur",    code:"INVALID_REQUIRED_FIELD", message:"Salary above grade ceiling (€140,000)" },
  { row:502, field:"iban",          code:"INVALID_IBAN",           message:"IBAN length 19, expected 27 for FR" },
  { row:603, field:"start_date",    code:"MISSING_REQUIRED_FIELD", message:"start_date is required" },
  { row:741, field:"contract_type", code:"INVALID_CONTRACT_TYPE",  message:"Got '', expected CDI/CDD/STAGE" },
  { row:802, field:"email",         code:"INVALID_EMAIL",          message:"Local part too long (>64 chars)" },
  { row:889, field:"position",      code:"REF_NOT_FOUND",          message:"Position 'Wizard II' not found" },
  { row:950, field:"iban",          code:"INVALID_IBAN",           message:"Checksum failed" },
  { row:1042,field:"manager_email", code:"INVALID_EMAIL",          message:"User not found in directory" },
  { row:1188,field:"salary_eur",    code:"INVALID_REQUIRED_FIELD", message:"Non-numeric value 'TBD'" },
]

export const BATCHES: Batch[] = Array.from({ length: 12 }, (_, i) => {
  const start = i * 100 + 1
  const end = Math.min(start + 99, 1178)
  const failed = [0,1,2,4,1,0,3,1,2,0,1,3][i] ?? 0
  return { batch:i+1, start, end, status: i < 5 ? "completed" : i === 5 ? "running" : "pending", success:(end-start+1)-failed, failed }
})

export const RECENT_RUNS: RecentRun[] = [
  { id:"run_8f3c1a90b27e", name:"northwind-prod-2026-05.har", source:"HAR",  status:"completed", endpoints:15, created:"2026-05-19 14:22", duration:"42s" },
  { id:"run_4a1b9d7e6c12", name:"hrcore-staging-jmeter.jmx", source:"JMX",  status:"completed", endpoints:9,  created:"2026-05-18 11:04", duration:"31s" },
  { id:"run_c92ef0a4b813", name:"live-capture-payroll-q2",   source:"Live", status:"parsing",   endpoints:7,  created:"2026-05-20 09:58", duration:"—" },
  { id:"run_55fa11d7902e", name:"acme-checkout-v3.har",      source:"HAR",  status:"failed",    endpoints:0,  created:"2026-05-17 16:40", duration:"4s" },
  { id:"run_3d7c8eaf201b", name:"partners-api-march.har",    source:"HAR",  status:"completed", endpoints:23, created:"2026-05-15 10:11", duration:"58s" },
]

export const RUN_OPTIONS: RunOption[] = [
  { id:"run_8f3c1a90b27e", label:"Analyse #001 — northwind-prod (20 mai 2026)", short:"Analyse #001" },
  { id:"run_4a1b9d7e6c12", label:"Analyse #002 — hrcore-staging (18 mai 2026)", short:"Analyse #002" },
  { id:"run_c92ef0a4b813", label:"Analyse #003 — payroll-q2 (en cours)",        short:"Analyse #003" },
  { id:"run_3d7c8eaf201b", label:"Analyse #004 — partners-api (15 mai 2026)",   short:"Analyse #004" },
]

export const AUTO_RUN_OPTIONS: AutoRunOption[] = [
  { id:"arun_b71d9e2c", label:"Automation Bulk #001 — Onboarding (20 mai 2026)" },
  { id:"arun_3f88a014", label:"Automation Simple #001 — Test onboarding (19 mai 2026)" },
  { id:"arun_92ab1c44", label:"Automation Bulk #002 — Migration de département (19 mai 2026)" },
  { id:"arun_7e0fb251", label:"Automation Bulk #003 — Offboarding (18 mai 2026)" },
  { id:"arun_a8c12d96", label:"Automation Bulk #004 — Ajustement salarial (17 mai 2026)" },
]

export const RECENT_AUTOMATIONS: RecentAutomation[] = [
  { id:"arun_b71d9e2c", workflow:"Employee Onboarding",  rows:1200, success:1178, failed:0,   status:"running",   started:"2026-05-20 10:14", dryRun:false },
  { id:"arun_3f88a014", workflow:"Employee Onboarding",  rows:42,   success:42,   failed:0,   status:"completed", started:"2026-05-19 16:22", dryRun:true },
  { id:"arun_92ab1c44", workflow:"Department Migration", rows:340,  success:331,  failed:9,   status:"completed", started:"2026-05-19 09:08", dryRun:false },
  { id:"arun_7e0fb251", workflow:"Employee Offboarding", rows:18,   success:18,   failed:0,   status:"completed", started:"2026-05-18 14:55", dryRun:false },
  { id:"arun_a8c12d96", workflow:"Salary Adjustment",   rows:215,  success:0,    failed:215, status:"failed",    started:"2026-05-17 11:30", dryRun:false },
]

export const APPROVALS: Approval[] = [
  { id:"ar_19f4", run:"arun_b71d9e2c", workflow:"Employee Onboarding",  rows:1178, invalid:22, risk:"high",     requestedBy:"camille.brun", requestedAt:"12 min ago", methods:["POST","PUT"],  targets:["/employees","/payroll/accounts","/payroll/accounts/{id}/iban","/access/badges","/notifications/welcome"] },
  { id:"ar_22a8", run:"arun_60e8c1a3", workflow:"Salary Adjustment",    rows:215,  invalid:0,  risk:"critical", requestedBy:"diane.osei",   requestedAt:"38 min ago", methods:["PATCH"],       targets:["/employees/{id}","/payroll/accounts/{id}"] },
  { id:"ar_31c2", run:"arun_9a3f0c1d", workflow:"Department Migration", rows:340,  invalid:9,  risk:"medium",   requestedBy:"sam.dupont",   requestedAt:"1 hr ago",   methods:["PATCH"],       targets:["/employees/{id}"] },
]

export const USERS: User[] = [
  { name:"Aria Mendes",    email:"aria.mendes@northwind.io",     role:"admin",               status:"active" },
  { name:"Camille Brun",   email:"camille.brun@northwind.io",    role:"business_user",       status:"active" },
  { name:"Diane Osei",     email:"diane.osei@northwind.io",      role:"approver",            status:"active" },
  { name:"Étienne Laval",  email:"etienne.laval@northwind.io",   role:"api_analyst",         status:"active" },
  { name:"Farah Haddad",   email:"farah.haddad@northwind.io",    role:"automation_operator", status:"active" },
  { name:"Gabriel Costa",  email:"gabriel.costa@northwind.io",   role:"auditor",             status:"active" },
  { name:"Hiroshi Sato",   email:"hiroshi.sato@northwind.io",    role:"api_analyst",         status:"pending" },
  { name:"Ines Ferreira",  email:"ines.ferreira@northwind.io",   role:"business_user",       status:"pending" },
]

export const ROLES: Record<Role, RoleInfo> = {
  admin:               { label:"Admin",              swatch:"#8b5cf6", description:"Sees everything" },
  api_analyst:         { label:"API Analyst",        swatch:"#6366f1", description:"Discovers & documents APIs" },
  business_user:       { label:"Business User",      swatch:"#06b6d4", description:"Drives bulk automations" },
  approver:            { label:"Approver",           swatch:"#f97316", description:"Reviews & approves runs" },
  automation_operator: { label:"Operator",           swatch:"#22c55e", description:"Executes approved runs" },
  auditor:             { label:"Auditor",            swatch:"#64748b", description:"Read-only" },
}

export const SUCCESS_TIMELINE = [
  { day:"Mon", success:142, failed:4 },
  { day:"Tue", success:188, failed:6 },
  { day:"Wed", success:230, failed:12 },
  { day:"Thu", success:295, failed:9 },
  { day:"Fri", success:312, failed:7 },
  { day:"Sat", success:91,  failed:2 },
  { day:"Sun", success:64,  failed:1 },
]

export const OPENAPI_DOC = {
  openapi:"3.1.0",
  info:{ title:"Northwind HR API", version:"2.0.0", description:"Auto-generated by ARIA from HAR capture run_8f3c1a90b27e on 2026-05-20." },
  servers:[{ url:"https://hr-api.northwind.io" }],
  paths:{
    "/api/v1/employees":{
      get:{ summary:"List employees", operationId:"hr.employees.list", responses:{ "200":{ description:"OK" } } },
      post:{ summary:"Create employee", operationId:"hr.employees.create", requestBody:{ required:true, content:{ "application/json":{ schema:{ $ref:"#/components/schemas/Employee" } } } }, responses:{ "201":{ description:"Created" }, "422":{ description:"Validation error" } } }
    },
    "/api/v1/employees/{employee_id}/contracts":{ post:{ summary:"Attach contract", operationId:"hr.contracts.create", responses:{ "201":{ description:"Created" } } } },
    "/api/v1/payroll/accounts":{ post:{ summary:"Open payroll account", operationId:"payroll.account.create", responses:{ "201":{ description:"Created" } } } },
    "/api/v1/access/badges":{ post:{ summary:"Issue building badge", operationId:"access.badge.issue", responses:{ "201":{ description:"Created" }, "409":{ description:"Already exists" } } } }
  },
  components:{
    schemas:{
      Employee:{ type:"object", required:["firstName","lastName","contactEmail","departmentRef","positionRef","contract"], properties:{ firstName:{ type:"string" }, lastName:{ type:"string" }, contactEmail:{ type:"string", format:"email" }, departmentRef:{ type:"string" }, positionRef:{ type:"string" }, contract:{ $ref:"#/components/schemas/Contract" } } },
      Contract:{ type:"object", required:["type","startDate","salary"], properties:{ type:{ type:"string", enum:["CDI","CDD","STAGE"] }, startDate:{ type:"string", format:"date" }, salary:{ type:"number" } } }
    }
  }
}
