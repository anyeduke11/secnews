import '@testing-library/jest-dom';

// Node >=22 在 globalThis 上预置了 localStorage 访问器 (--localstorage-file 未提供时
// 取值为 undefined 并发 ExperimentalWarning), vitest jsdom 环境注入全局时会因该属性
// 已存在而跳过, 导致组件内裸调用 localStorage.getItem 崩溃 (OnboardingHint 及其宿主
// OutboxMode/ReviewMode/Phase13ModeComponents)。此处显式恢复 jsdom 的实现;
// 若 window.localStorage 也不可用, 退化为内存 Storage 兜底。
if (typeof globalThis.localStorage === 'undefined' || globalThis.localStorage === null) {
  const fromWindow = (globalThis as unknown as { window?: { localStorage?: Storage } })
    .window?.localStorage;
  const storage: Storage =
    fromWindow ??
    (() => {
      const store = new Map<string, string>();
      return {
        getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
        setItem: (k: string, v: string) => void store.set(k, String(v)),
        removeItem: (k: string) => void store.delete(k),
        clear: () => void store.clear(),
        key: (i: number) => Array.from(store.keys())[i] ?? null,
        get length() {
          return store.size;
        },
      } satisfies Storage;
    })();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage,
  });
}
