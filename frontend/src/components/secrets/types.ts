/**
 * secrets/types — SecretsPage 共享类型定义。
 *
 * 拆自原 SecretsPage.tsx (794 行): 页面 props 与表单提交请求类型。
 * 纯结构拆分, 类型定义与原文件等价。
 */
export interface SecretsPageProps {
  onBack: () => void;
}

/** 新增/编辑密钥表单的提交请求 (原 AddOrEditForm props 内联类型)。 */
export interface SecretFormRequest {
  name: string;
  model: string;
  base_url: string;
  api_key: string;
  master_key: string;
}
