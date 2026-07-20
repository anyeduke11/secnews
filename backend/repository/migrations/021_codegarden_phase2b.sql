-- 021_codegarden_phase2b.sql — Phase 2b CodeGarden Service Mesh
-- PRD: docs/CodeGarden_PRD_v2.0.md §5.2/§5.3/§5.4 + §6.2.5/§6.2.6/§6.2.7
-- spec: .trae/specs/phase2b-service-mesh/spec.md §3.1
--
-- 新增 4 张表 (M2 服务网格 + M3 资源中枢 + M4 联动引擎)：
--   cg_services       — 服务注册表 (lsof/docker/pm2 自动发现 + 手动注册)
--   cg_resources      — 资源池 (port/domain/env_template/volume 4 类)
--   cg_dependencies   — 依赖图谱 (project/service 间 code/service/data 依赖)
--   cg_events         — 事件总线 (pending → processed 异步处理)

-- ============================================================================
-- cg_services: M2 服务网格 (PRD 6.2.5)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_services (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES cg_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    namespace TEXT,                    -- 如 ai-assistant.web
    type TEXT NOT NULL,                -- http / websocket / grpc / static / database
    runtime TEXT NOT NULL,             -- docker / pm2 / system / bare
    status TEXT NOT NULL,              -- running / stopped / error / unknown
    endpoint_host TEXT,
    endpoint_port INTEGER,
    endpoint_domain TEXT,
    health_check_type TEXT,            -- http / tcp / script
    health_check_path TEXT,
    health_check_interval INTEGER DEFAULT 30,
    cpu_limit TEXT,
    memory_limit TEXT,
    dependencies TEXT,                 -- JSON array of service ids (冗余, 主存 cg_dependencies)
    env_vars TEXT,                     -- JSON
    created_at TEXT NOT NULL,
    last_checked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_services_project ON cg_services(project_id);
CREATE INDEX IF NOT EXISTS idx_cg_services_status ON cg_services(status);
CREATE INDEX IF NOT EXISTS idx_cg_services_namespace ON cg_services(namespace);

-- ============================================================================
-- cg_resources: M3 资源中枢 (PRD 6.2.6)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_resources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,                -- port / domain / env_template / volume
    value TEXT NOT NULL,               -- 端口号 / 域名 / 模板名 / 卷名
    status TEXT NOT NULL,              -- allocated / free / reserved
    owner_service_id TEXT REFERENCES cg_services(id) ON DELETE SET NULL,
    owner_project_id TEXT REFERENCES cg_projects(id) ON DELETE SET NULL,
    metadata TEXT,                     -- JSON
    reserved_until TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cg_resources_type ON cg_resources(type);
CREATE INDEX IF NOT EXISTS idx_cg_resources_owner ON cg_resources(owner_service_id, owner_project_id);
CREATE INDEX IF NOT EXISTS idx_cg_resources_status ON cg_resources(status);

-- ============================================================================
-- cg_dependencies: M4 联动引擎 - 依赖图谱 (PRD 6.2.7)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_dependencies (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,         -- project / service
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,         -- project / service
    target_id TEXT NOT NULL,
    dep_type TEXT NOT NULL,            -- code / service / data
    metadata TEXT,                     -- JSON
    created_at TEXT NOT NULL,
    UNIQUE(source_type, source_id, target_type, target_id, dep_type)
);

CREATE INDEX IF NOT EXISTS idx_cg_deps_source ON cg_dependencies(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_cg_deps_target ON cg_dependencies(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_cg_deps_type ON cg_dependencies(dep_type);

-- ============================================================================
-- cg_events: M4 联动引擎 - 事件总线 (PRD §5.4.2, §6.2 未建, Phase 2b 补)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,          -- code_push / service_error / port_conflict / dep_update / project_archive
    source_type TEXT NOT NULL,         -- project / service / resource / scheduler
    source_id TEXT NOT NULL,
    payload TEXT,                      -- JSON
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / processed / failed
    created_at TEXT NOT NULL,
    processed_at TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_events_type ON cg_events(event_type);
CREATE INDEX IF NOT EXISTS idx_cg_events_status ON cg_events(status);
CREATE INDEX IF NOT EXISTS idx_cg_events_created ON cg_events(created_at);
CREATE INDEX IF NOT EXISTS idx_cg_events_source ON cg_events(source_type, source_id);
