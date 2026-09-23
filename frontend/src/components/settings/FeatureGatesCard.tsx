/**
 * FeatureGatesCard — 能力开关卡 (P2 可写化: toggle 已接通 PUT)
 *
 * 数据源 GET /api/settings/feature-gates (per-gate enabled + source + effective_scope);
 * toggle 调 PUT /api/settings/feature-gates/{name}: 成功后行内更新状态并显示 note;
 * 失败 (409 env 覆盖拒绝 / 404 未知键) 行内展示错误 message。
 * source=env 的 gate switch 禁用 — env > TOML, 写 TOML 无效。
 * 语义: TOML 写入后运行时读数 5s 内跟随; 路由注册/job 调度为启动快照, 需重启。
 */
import { useCallback, useEffect, useState } from 'react';
import { ApiError, apiFetch, getJSON } from '../../lib/api';

interface GateItem {
  name: string;
  enabled: boolean;
  source: 'default' | 'toml' | 'env';
  effective_scope: 'runtime' | 'startup';
}

interface RowNote {
  kind: 'ok' | 'error';
  text: string;
}

const GATE_DESCS: Record<string, string> = {
  secnews: '情报核心: 三层工作流/判读台/知识管线',
  codegarden: '代码花园视图',
  codegarden_phase2b: 'CodeGarden 运维层 (服务网格/资源中枢)',
  mcp: 'MCP 工具面 (agent 适配端点)',
  sync: 'WebDAV 跨设备同步',
  tech_stack: '技术栈图谱',
  security_graph: 'ATT&CK / CVE 安全图谱',
  dsh: 'dsh 认知大脑 (受管子进程)',
  info_filter: '独立资讯筛选门禁',
  skill_registry: 'Skill 商店',
  trigger_gate: '触发源门禁 (webhook/KL/collector)',
  user_skills: '用户自建 Skill',
  interest_engine: '兴趣引擎 (行为信号+域权重)',
  semantic_filter: '语义筛选',
  ai_classify: 'AI 分类',
  pipeline_ner: '管线 NER 实体抽取',
};

export function FeatureGatesCard() {
  const [gates, setGates] = useState<GateItem[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [rowNote, setRowNote] = useState<{ name: string; note: RowNote } | null>(null);

  useEffect(() => {
    let dead = false;
    getJSON<{ items?: GateItem[] }>('/api/settings/feature-gates')
      .then(d => { if (!dead) setGates(d.items ?? []); })
      .catch(() => { if (!dead) setGates([]); });
    return () => { dead = true; };
  }, []);

  const toggle = useCallback(async (gate: GateItem) => {
    const next = !gate.enabled;
    setBusy(gate.name);
    setRowNote(null);
    try {
      const resp = await apiFetch<{ note?: string }>(
        `/api/settings/feature-gates/${encodeURIComponent(gate.name)}`,
        { method: 'PUT', body: JSON.stringify({ enabled: next }) },
      );
      setGates(prev => prev?.map(g => (g.name === gate.name ? { ...g, enabled: next } : g)) ?? prev);
      setRowNote({ name: gate.name, note: { kind: 'ok', text: resp.note ?? '已写入 TOML' } });
    } catch (e) {
      const msg = e instanceof ApiError && e.message ? e.message : '写入失败';
      setRowNote({ name: gate.name, note: { kind: 'error', text: msg } });
    } finally {
      setBusy(null);
    }
  }, []);

  // GATE_DESCS 16 键常量驱动顺序 (描述层); 后端 items 为事实源
  const byName = new Map((gates ?? []).map(g => [g.name, g]));
  const keys = Object.keys(GATE_DESCS);

  return (
    <div className="st-card">
      <h3>能力开关</h3>
      <p className="st-section-desc">
        源：<code className="st-code">backend/config/feature_gates.toml</code>。
        改动经 TOML 写入后 5s 内影响运行时读数；路由注册与定时任务需重启后端生效。
      </p>
      {gates === null ? (
        <p className="st-cellnote">载入中…</p>
      ) : keys.length === 0 || gates.length === 0 ? (
        <p className="st-cellnote">未能读取能力开关 — 后端不可达时不显示默认值，以免误判。</p>
      ) : (
        <div className="st-rule-list">
          {keys.map(k => {
            const gate = byName.get(k);
            if (!gate) return null;
            const on = gate.enabled;
            const envLocked = gate.source === 'env';
            const note = rowNote?.name === k ? rowNote.note : null;
            return (
              <div className="st-rule" key={k}>
                <div>
                  <p className="st-label">{k}</p>
                  <p className="st-fcode">
                    {GATE_DESCS[k]}
                    {envLocked && '（HOTSPOT_FEATURE_GATES env 覆盖中，TOML 写入无效）'}
                  </p>
                </div>
                <div className="st-ctrl">
                  <button
                    type="button"
                    className="st-switch"
                    role="switch"
                    aria-checked={on}
                    disabled={envLocked || busy === k}
                    aria-label={`${k}：${on ? '已启用' : '已停用'}${envLocked ? '（env 覆盖，只读）' : ''}`}
                    onClick={() => { void toggle(gate); }}
                  />
                  <span className={`st-chip${on ? ' ok' : ''}`}><i aria-hidden />{on ? 'ON' : 'OFF'}</span>
                </div>
                {note && (
                  <p className="st-cellnote" role="status" style={note.kind === 'error' ? { color: 'var(--sn-red, #c0392b)' } : undefined}>
                    {note.text}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
