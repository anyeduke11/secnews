/**
 * FeatureGatesCard — 能力开关卡 (原 sentinel 只读控制台 Tab2 可写化第一期)
 *
 * P1: 16 gate 全量只读呈现 (数据源 GET /api/settings/features); toggle disabled,
 * 注明 TOML 来源与重启语义。P2: /api/settings/feature-gates/{name} PUT 就绪后接通。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';

type FeatureMap = Record<string, boolean>;

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
  const [features, setFeatures] = useState<FeatureMap | null>(null);

  useEffect(() => {
    let dead = false;
    getJSON<FeatureMap>('/api/settings/features')
      .then(d => { if (!dead) setFeatures(d ?? {}); })
      .catch(() => { if (!dead) setFeatures({}); });
    return () => { dead = true; };
  }, []);

  const keys = Object.keys(GATE_DESCS);

  return (
    <div className="st-card">
      <h3>能力开关</h3>
      <p className="st-section-desc">
        源：<code className="st-code">backend/config/feature_gates.toml</code>。
        改动经 TOML 写入后 5s 内影响运行时读数；路由注册与定时任务需重启后端生效。
      </p>
      {features === null ? (
        <p className="st-cellnote">载入中…</p>
      ) : keys.length === 0 ? (
        <p className="st-cellnote">未能读取能力开关 — 后端不可达时不显示默认值，以免误判。</p>
      ) : (
        <div className="st-rule-list">
          {keys.map(k => {
            const on = Boolean(features[k]);
            return (
              <div className="st-rule" key={k}>
                <div>
                  <p className="st-label">{k}</p>
                  <p className="st-fcode">{GATE_DESCS[k]}</p>
                </div>
                <div className="st-ctrl">
                  <button
                    type="button"
                    className="st-switch"
                    role="switch"
                    aria-checked={on}
                    disabled
                    aria-label={`${k}：${on ? '已启用' : '已停用'}（只读）`}
                  />
                  <span className={`st-chip${on ? ' ok' : ''}`}><i aria-hidden />{on ? 'ON' : 'OFF'}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
