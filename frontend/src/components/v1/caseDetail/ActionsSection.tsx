/**
 * ActionsSection — 行动 (Action) + 运行 (Run) + 产物 (Artifact) 区块 + D2 SK-03 真实出稿入口
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/data-testid/section 锚点逐字不变)
 *
 * 数据全部由容器单点 aggregate 下发 (actions / runs / artifacts), 本区块不发任何请求;
 * 6 个 mutation 按钮走 allowed_actions 守卫, handler 由容器注入。
 */
import type { Judgment } from '../../../domain/v1_0';
import type { Action, Artifact, Run } from '../../../api/v1';
import { renderInlineMarkdown } from '../../../lib/markdown';
import { Badge } from './CaseBadge';

interface Props {
  actions: Action[];
  runs: Run[];
  artifacts: Artifact[];
  judgments: Judgment[];
  loading: boolean;
  generating: 'judgment' | 'action' | null;
  pendingMutation: string | null;
  onGenerate: () => void;
  onApprove: (a: Action) => void;
  onStart: (a: Action) => void;
  onCancel: (a: Action) => void;
  onVerify: (art: Artifact) => void;
  onAccept: (art: Artifact) => void;
  onReject: (art: Artifact) => void;
}

export function ActionsSection({
  actions, runs, artifacts, judgments, loading, generating, pendingMutation,
  onGenerate, onApprove, onStart, onCancel, onVerify, onAccept, onReject,
}: Props) {
  return (
    <div id="section-actions" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          行动 (Action) + 运行 (Run) + 产物 (Artifact) {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
        {/* D2: SK-03 真实出稿 — 引用 published 判断 (§10.1) */}
        <button
          type="button"
          onClick={onGenerate}
          disabled={generating !== null || !judgments.some(j => j.status === 'published')}
          title={judgments.some(j => j.status === 'published') ? 'SK-03 inspection-materials' : '需先生成并发布判断 (§10.1)'}
          className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
          style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
          data-testid="generate-action-btn"
        >
          {generating === 'action' ? '生成中…' : '生成行动 (SK-03)'}
        </button>
      </div>
      {actions.length === 0 ? (
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无行动</div>
      ) : (
        <div className="space-y-4">
          {actions.map(a => {
            const actionRuns = runs.filter(r => r.action_id === a.id);
            const actionArtifacts = artifacts.filter(art => actionRuns.some(r => r.id === art.run_id));
            return (
              <div key={a.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{a.title}</span>
                  <Badge color={a.status === 'succeeded' ? 'green' : a.status === 'failed' ? 'red' : a.status === 'running' ? 'blue' : a.status === 'approved' ? 'yellow' : 'gray'}>{a.status}</Badge>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>rev {a.revision}</span>
                </div>
                <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
                  {a.id} · plan_hash: {a.plan_hash?.slice(0, 12) ?? '-'}…
                  {a.expected_artifacts && a.expected_artifacts.length > 0 && (
                    <> · 预期产物: {a.expected_artifacts.join(', ')}</>
                  )}
                </div>

                {/* C10 R14/R15: 行动 mutation 按钮 (走 allowed_actions 守卫) */}
                {Array.isArray((a as any).allowed_actions) && (a as any).allowed_actions.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {(a as any).allowed_actions.includes('approve') && (
                      <button
                        onClick={() => onApprove(a)}
                        disabled={pendingMutation === `approve:${a.id}`}
                        className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                        style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
                        data-testid="approve-action-btn"
                      >
                        {pendingMutation === `approve:${a.id}` ? '批准中…' : '批准'}
                      </button>
                    )}
                    {(a as any).allowed_actions.includes('start') && (
                      <button
                        onClick={() => onStart(a)}
                        disabled={pendingMutation === `start:${a.id}`}
                        className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                        style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                        data-testid="start-action-btn"
                      >
                        {pendingMutation === `start:${a.id}` ? '启动中…' : '启动'}
                      </button>
                    )}
                    {(a as any).allowed_actions.includes('cancel') && (
                      <button
                        onClick={() => onCancel(a)}
                        disabled={pendingMutation === `cancel:${a.id}`}
                        className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                        style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)', border: '1px solid var(--line)' }}
                        data-testid="cancel-action-btn"
                      >
                        {pendingMutation === `cancel:${a.id}` ? '取消中…' : '取消'}
                      </button>
                    )}
                  </div>
                )}

                {/* plan (T11 markdown 渲染) */}
                {a.plan && (
                  <details className="mb-2">
                    <summary className="text-xs cursor-pointer" style={{ color: 'var(--text-muted)' }}>查看 plan</summary>
                    <div
                      className="text-xs mt-1 p-2 rounded prose-sm"
                      style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)' }}
                      dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(a.plan) }}
                    />
                  </details>
                )}

                {/* 运行 */}
                {actionRuns.length > 0 && (
                  <div className="mb-3">
                    <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>运行 ({actionRuns.length} 次):</div>
                    {actionRuns.map(r => (
                      <div key={r.id} className="flex items-center gap-2 text-xs">
                        <Badge color={r.status === 'succeeded' ? 'green' : r.status === 'failed' ? 'red' : r.status === 'cancelled' ? 'gray' : 'blue'}>{r.status}</Badge>
                        <span className="font-mono" style={{ color: 'var(--text-muted)' }}>attempt #{r.attempt} · {r.protocol}</span>
                        <span style={{ color: 'var(--text-muted)' }}>{r.id}</span>
                        {r.error && <span style={{ color: 'var(--color-error)' }}>错误: {r.error.slice(0, 80)}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* 产物 */}
                {actionArtifacts.length > 0 ? (
                  <div>
                    <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>产物 ({actionArtifacts.length} 条):</div>
                    <div className="space-y-1">
                      {actionArtifacts.map(art => (
                        <div key={art.id} className="flex items-center gap-2 text-xs flex-wrap">
                          <span style={{ color: 'var(--text-primary)' }}>{art.title}</span>
                          <Badge color={art.status === 'accepted' ? 'green' : art.status === 'verified' ? 'blue' : art.status === 'rejected' ? 'red' : art.status === 'superseded' ? 'gray' : 'yellow'}>{art.status}</Badge>
                          <span style={{ color: 'var(--text-muted)' }}>{art.format} · {(art.size_bytes / 1024).toFixed(1)}KB</span>
                          {art.verified_result && <span style={{ color: 'var(--text-muted)' }}>· 验证: {art.verified_result}</span>}
                          {art.accepted_by && <span style={{ color: 'var(--text-success, var(--color-success))' }}>· 验收: {art.accepted_by}</span>}
                          {/* C10 R08/R14/R15: 产物 mutation 按钮 (accept 必先 verify — 走 allowed_actions 守卫) */}
                          {Array.isArray((art as any).allowed_actions) && (art as any).allowed_actions.length > 0 && (
                            <span className="flex gap-1.5 ml-auto">
                              {(art as any).allowed_actions.includes('verify') && (
                                <button
                                  onClick={() => onVerify(art)}
                                  disabled={pendingMutation === `verify:${art.id}`}
                                  className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                  style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
                                  data-testid="verify-artifact-btn"
                                >
                                  {pendingMutation === `verify:${art.id}` ? '验证中…' : '验证'}
                                </button>
                              )}
                              {(art as any).allowed_actions.includes('accept') && (
                                <button
                                  onClick={() => onAccept(art)}
                                  disabled={pendingMutation === `accept:${art.id}`}
                                  className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                  style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                                  data-testid="accept-artifact-btn"
                                >
                                  {pendingMutation === `accept:${art.id}` ? '验收中…' : '业务验收'}
                                </button>
                              )}
                              {(art as any).allowed_actions.includes('reject') && (
                                <button
                                  onClick={() => onReject(art)}
                                  disabled={pendingMutation === `reject:${art.id}`}
                                  className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                  style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)', border: '1px solid var(--line)' }}
                                  data-testid="reject-artifact-btn"
                                >
                                  {pendingMutation === `reject:${art.id}` ? '拒绝中…' : '拒绝'}
                                </button>
                              )}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-xs p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                    缺资产: 此行动无产出产物 (baseline §5: 材料生成 ≠ 排查完成)
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
