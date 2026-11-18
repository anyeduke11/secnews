/**
 * KnowledgeImport — 信息导入子页面
 *
 * 涵盖多源信息采集:
 *  - Cubox 同步 (含实时进度)
 *  - 浏览器书签导入 (JSON / HTML, 可选 URL 验证)
 *  - 打开 Obsidian 知识库
 *  - 查看同步冲突快照
 *
 * B5 拆分: 本文件只保留容器 (状态 + 取数/轮询编排); 展示区块在 ./import/
 */
import { useState, useRef, type ChangeEvent } from 'react';
import {
  getKnowledgeTask,
  getObsidianConflicts,
  importCuboxCards,
  importCuboxDir,
  openObsidianVault,
  syncKnowledgeSource,
} from '../../api/knowledge';
import { KNOWLEDGE_AREAS } from './KnowledgeTabs';
import { ImportHero } from './import/ImportHero';
import { ImportProgressBar, ImportToast } from './import/ImportStatusBar';
import { CuboxImportCard } from './import/CuboxImportCard';
import { BookmarkImportCard, ObsidianCard, ConflictCard, ConflictSection } from './import/SourceCards';
import type { ConflictFile, CuboxTask, ImportToastMsg } from './import/importModel';

export function KnowledgeImport() {
  const [syncing, setSyncing] = useState(false);
  const [syncPhase, setSyncPhase] = useState('');
  const [syncCurrent, setSyncCurrent] = useState(0);
  const [syncTotal, setSyncTotal] = useState(0);
  const [syncElapsed, setSyncElapsed] = useState(0);
  const syncStartRef = useRef(0);
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [toast, setToast] = useState<ImportToastMsg | null>(null);
  // C2 (DEV-0195): cubox CLI 导出导入 + 本地目录导入
  const [cliBusy, setCliBusy] = useState(false);
  const [dirPath, setDirPath] = useState('');
  const [dirBusy, setDirBusy] = useState(false);
  const cliFileRef = useRef<HTMLInputElement | null>(null);
  const [conflicts, setConflicts] = useState<ConflictFile[] | null>(null);

  const area = KNOWLEDGE_AREAS.find(a => a.key === 'import')!;

  const stopSyncProgress = () => {
    if (syncPollRef.current) {
      clearInterval(syncPollRef.current);
      syncPollRef.current = null;
    }
  };

  const flashToast = (t: ImportToastMsg) => {
    setToast(t);
    setTimeout(() => setToast(null), 5000);
  };

  const handleSync = () => {
    setSyncing(true);
    setSyncPhase('pending');
    setSyncCurrent(0);
    setSyncTotal(0);
    setSyncElapsed(0);
    syncStartRef.current = Date.now();

    const elapsedTimer = setInterval(() => {
      setSyncElapsed(Math.round((Date.now() - syncStartRef.current) / 1000));
    }, 1000);

    // 非 2xx 由 apiFetch 抛错 (message 经 getApiErrorMessage 兜底), 网络异常走 catch
    syncKnowledgeSource('cubox')
      .then(data => {
        const taskId = data?.task_id;
        if (!taskId) throw new Error('no task_id returned');
        syncPollRef.current = setInterval(() => {
          getKnowledgeTask<CuboxTask>(taskId)
            .then(task => {
              const params = task?.params || {};
              const phase = params?.phase || task?.status || 'pending';
              setSyncPhase(phase);
              setSyncCurrent(params?.current || 0);
              setSyncTotal(params?.total || 0);
              if (task?.status === 'done') {
                clearInterval(elapsedTimer);
                stopSyncProgress();
                const result = params?.result || {};
                const newCount = result?.new ?? 0;
                const merged = result?.merged ?? 0;
                const total = newCount + merged;
                const elapsed = Math.round((Date.now() - syncStartRef.current) / 1000);
                flashToast({
                  kind: 'ok',
                  msg: total === 0
                    ? `✓ 同步完成，无新条目 (${elapsed}s)`
                    : `✓ 同步完成：${newCount} 新增 / ${merged} 合并 (${elapsed}s)`,
                });
                setSyncing(false);
                setSyncPhase('done');
                setTimeout(() => setSyncPhase(''), 1000);
              } else if (task?.status === 'failed') {
                clearInterval(elapsedTimer);
                stopSyncProgress();
                flashToast({ kind: 'err', msg: `✗ 同步失败: ${task?.error_message || '未知错误'}` });
                setSyncing(false);
              }
            })
            .catch(() => { /* 轮询网络错误忽略 */ });
        }, 1500);
      })
      .catch(e => {
        clearInterval(elapsedTimer);
        stopSyncProgress();
        flashToast({ kind: 'err', msg: `✗ 同步失败: ${e?.message || String(e)}` });
        setSyncing(false);
      });
  };

  // C2 兜底 ①: 上传 cubox-cli 导出的 JSON
  const handleCliFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        const cards = Array.isArray(parsed) ? parsed : parsed?.cards;
        if (!Array.isArray(cards) || cards.length === 0) {
          flashToast({ kind: 'err', msg: '文件形状不符：期望卡片数组或 {cards: [...]}' });
          return;
        }
        setCliBusy(true);
        const r = await importCuboxCards({ cards });
        flashToast({ kind: 'ok', msg: `已导入 ${r.imported ?? 0} 条（新建 ${r.new ?? 0} · 合并 ${r.merged ?? 0}）` });
      } catch (err) {
        flashToast({ kind: 'err', msg: `导入失败: ${err instanceof Error ? err.message : String(err)}` });
      } finally {
        setCliBusy(false);
      }
    };
    reader.readAsText(file);
  };

  // C2 兜底 ②: 导入本地 Cubox 知识库目录
  const handleDirImport = async () => {
    if (!dirPath.trim() || dirBusy) return;
    setDirBusy(true);
    try {
      const r = await importCuboxDir({ path: dirPath.trim() });
      flashToast({ kind: 'ok', msg: `目录导入完成: ${r.cards ?? 0} 卡 → 入库 ${r.imported ?? 0} 条（新建 ${r.new ?? 0} · 合并 ${r.merged ?? 0}）` });
    } catch (err) {
      flashToast({ kind: 'err', msg: `目录导入失败: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setDirBusy(false);
    }
  };

  const handleOpenObsidian = () => {
    openObsidianVault()
      .then(data => {
        if (data?.url) {
          window.location.href = data.url;
        } else {
          flashToast({ kind: 'err', msg: '✗ Obsidian URL 缺失' });
        }
      })
      .catch(e => {
        flashToast({ kind: 'err', msg: `✗ 打开 Obsidian 失败: ${e?.message || String(e)}` });
      });
  };

  const handleViewConflicts = () => {
    if (conflicts !== null) {
      setConflicts(null);
      return;
    }
    getObsidianConflicts()
      .then(data => {
        setConflicts(Array.isArray(data?.conflicts) ? data.conflicts : []);
      })
      .catch(e => {
        flashToast({ kind: 'err', msg: `✗ 加载冲突失败: ${e?.message || String(e)}` });
      });
  };

  return (
    <div
      className="space-y-3"
      style={
        {
          '--area-accent': area.accentVar,
        } as React.CSSProperties
      }
      data-area-page="import"
    >
      <ImportHero />

      {/* 同步进度条 */}
      {syncing && (
        <ImportProgressBar
          phase={syncPhase}
          current={syncCurrent}
          total={syncTotal}
          elapsed={syncElapsed}
        />
      )}

      {/* Toast */}
      {toast && <ImportToast toast={toast} />}

      {/* 数据源 action cards */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <CuboxImportCard
          syncing={syncing}
          cliBusy={cliBusy}
          dirBusy={dirBusy}
          dirPath={dirPath}
          fileRef={cliFileRef}
          onSync={handleSync}
          onDirPathChange={setDirPath}
          onCliFileChange={handleCliFile}
          onDirImport={handleDirImport}
        />
        <BookmarkImportCard />
        <ObsidianCard onOpen={handleOpenObsidian} />
        <ConflictCard revealed={conflicts !== null} onToggle={handleViewConflicts} />
      </section>

      {/* 冲突列表展开 */}
      {conflicts !== null && <ConflictSection conflicts={conflicts} />}
    </div>
  );
}
