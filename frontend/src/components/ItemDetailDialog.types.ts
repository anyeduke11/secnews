// 拆分自 ItemDetailDialog.tsx: 弹窗对外 props 与标注实体的共享类型。
export interface ItemDetailDialogProps {
  item_id: string | null;
  onClose: () => void;
}

export type ItemAnnotation = { id: number; content: string; created_at?: string };