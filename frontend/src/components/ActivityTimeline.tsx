import { cn } from "../lib/utils";

/** 后端节点名 → 前端时间线显示文案（对应 PRD 8.6 事件节点表） */
const NODE_LABELS: Record<string, string> = {
  generate_plan: "生成调研计划",
  generate_search: "生成检索查询",
  web_search: "医药数据源检索（百炼/Firecrawl）",
  critique: "反思和分析",
  final_answer: "撰写报告与审稿",
};

interface ActivityTimelineProps {
  /** 已观察到的后端节点序列（按出现顺序，可能重复） */
  events: string[];
  isLoading: boolean;
}

export const ActivityTimeline: React.FC<ActivityTimelineProps> = ({
  events,
  isLoading,
}) => {
  if (events.length === 0) return null;

  // 压缩连续重复节点，保持可读性
  const compressed: { node: string; count: number }[] = [];
  for (const node of events) {
    const last = compressed[compressed.length - 1];
    if (last && last.node === node) last.count += 1;
    else compressed.push({ node, count: 1 });
  }

  return (
    <div className="rounded-lg border border-neutral-700 bg-neutral-800/60 px-4 py-3 mb-3">
      <p className="text-xs text-neutral-400 mb-2">调研进度</p>
      <ol className="flex flex-col gap-1.5">
        {compressed.map((e, idx) => {
          const isLast = idx === compressed.length - 1;
          return (
            <li key={idx} className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "inline-block h-2 w-2 rounded-full",
                  isLast && isLoading
                    ? "bg-sky-400 animate-pulse"
                    : "bg-emerald-500"
                )}
              />
              <span className="text-neutral-200">
                {NODE_LABELS[e.node] ?? e.node}
                {e.count > 1 && (
                  <span className="text-neutral-500"> ×{e.count}</span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      {isLoading && (
        <p className="text-xs text-neutral-500 mt-2">正在处理中，请稍候…</p>
      )}
    </div>
  );
};
