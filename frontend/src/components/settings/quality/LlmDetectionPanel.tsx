/**
 * quality/LlmDetectionPanel — LLM AI 内容检测 (DEV-0243 真实状态化)
 *
 * 历史: 此前面板有 quality.llm_enabled 假开关 (PUT /api/quality/rules 可写),
 * 但 v4.4 起门禁统一走 AIService (pipeline.build_context 不再读 settings),
 * 该键无任何消费方 — 且 GET /api/quality/rules 的 RULE_METADATA 不含此键,
 * 保存后刷新即回显 false, 造成"每次都重置"的错觉。
 *
 * 现状: 开关 = ai_service.available() (商汤 key 就绪或 ollama 在线),
 * 经 GET /api/llm/status 的 gate_detect_available 暴露。
 * 一次配置长期有效 = 密钥配进加密保险箱 (SecretsPanel) 或本地 ollama 常驻,
 * 无需任何面板开关。
 */
import { useState } from 'react';

export interface LlmDetectionStatus {
  gate_detect_available: boolean;
  effective_provider: string | null;
  key_source: string;
}

export interface LlmDetectionPanelProps {
  status: LlmDetectionStatus | null;
  loading: boolean;
}

const KEY_SOURCE_LABELS: Record<string, string> = {
  env: '环境变量',
  secrets: '加密保险箱',
  none: '未配置',
};

export function LlmDetectionPanel({ status, loading }: LlmDetectionPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const available = status?.gate_detect_available === true;
  const provider = status?.effective_provider ?? null;
  const keyLabel = KEY_SOURCE_LABELS[status?.key_source ?? ''] ?? status?.key_source ?? '未知';

  return (
    <section className="st-section" aria-label="LLM AI 内容检测" data-testid="llm-detection-panel">
      <h3>
        LLM AI 内容检测
        <span
          className={loading ? 'st-chip mute' : available ? 'st-chip ok' : 'st-chip mute'}
          title={loading ? '检测中' : `gate_detect_available: ${available}`}
          data-testid="llm-detect-state"
        >
          <i aria-hidden />{loading ? '检测中' : available ? '检测中' : '未启用'}
        </span>
      </h3>
      <p className="st-section-desc">
        启用后, 采集管线会用 LLM 对通过质量规则的热点做二次 AI 批量/软文识别
        (凭据就绪即自动启用, 无独立开关)。
      </p>
      <div className="st-section-body">
        {loading ? (
          <p className="st-label">读取 LLM 状态中…</p>
        ) : available ? (
          <div className="st-rule">
            <div>
              <p className="st-label">检测已生效</p>
              <p className="st-key">
                provider: {provider ?? '—'} · 密钥来源: {keyLabel}
              </p>
            </div>
          </div>
        ) : (
          <div className="st-rule">
            <div>
              <p className="st-label">检测未启用 — 完成任一项即长期生效</p>
              <p className="st-key">
                ① 商汤密钥配入下方加密保险箱 (SecretsPanel); 或 ② 本地启动 ollama (qwen2.5:7b)
              </p>
            </div>
          </div>
        )}
        <div className="st-actionbar">
          <button
            type="button"
            className="st-btn"
            onClick={() => setExpanded(v => !v)}
            aria-expanded={expanded}
          >
            {expanded ? '收起说明' : '为什么没有开关?'}
          </button>
        </div>
        {expanded && (
          <p className="st-section-desc" data-testid="llm-detect-explain">
            v4.4 起 AI 检测不再经设置页开关: 凭据统一走 ai_hub (env / 加密保险箱 / ollama),
            凭据就绪即自动启用, 失败 fail-open 不误伤资讯。
            旧版 quality.llm_enabled 开关无消费方, 已移除 (DEV-0243)。
          </p>
        )}
      </div>
    </section>
  );
}

export default LlmDetectionPanel;
