import { useState } from "react";

interface InputFormProps {
  onSubmit: (inputValue: string, effort: string, model: string) => void;
  onCancel: () => void;
  isLoading: boolean;
  hasHistory: boolean;
}

/**
 * 研究强度档位（PRD 8.4：低 1/1，中 3/3，高 5/10）。
 * 每个档位固定绑定一个模型，不可改选，界面只读展示。
 */
export const EFFORT_OPTIONS = [
  { value: "low", label: "低（快速了解）", model: "deepseek-v4.1-flash", modelLabel: "DeepSeek-V4.1-Flash" },
  { value: "medium", label: "中（常规调研）", model: "qwen3.8-flash", modelLabel: "Qwen3.8-Flash" },
  { value: "high", label: "高（深度专题）", model: "qwen3.8-max-0902", modelLabel: "Qwen3.8-Max-0902" },
];

export const InputForm: React.FC<InputFormProps> = ({
  onSubmit,
  onCancel,
  isLoading,
  hasHistory,
}) => {
  const [inputValue, setInputValue] = useState("");
  const [effort, setEffort] = useState("medium");

  // 模型由研究强度固定决定，无需用户选择
  const current = EFFORT_OPTIONS.find((o) => o.value === effort)!;

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!inputValue.trim() || isLoading) return;
    onSubmit(inputValue.trim(), effort, current.model);
    setInputValue("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full">
      <textarea
        className="w-full min-h-[96px] rounded-lg bg-neutral-800 border border-neutral-700 px-4 py-3 text-neutral-100 placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-sky-600"
        placeholder="梳理 GLP-1 赛道全球在研管线的竞争格局，重点关注临床阶段、给药方式差异与专利风险"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") handleSubmit();
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-neutral-400">研究强度</label>
        <select
          className="rounded-md bg-neutral-800 border border-neutral-700 px-3 py-2 text-sm"
          value={effort}
          onChange={(e) => setEffort(e.target.value)}
        >
          {EFFORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {/* 模型为强度固定绑定，只读展示（不可选择） */}
        <label className="text-sm text-neutral-400">模型</label>
        <span className="rounded-md bg-neutral-800/60 border border-neutral-700/60 px-3 py-2 text-sm text-neutral-300">
          {current.modelLabel}
        </span>

        <div className="flex-1" />

        {isLoading ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md bg-red-700 hover:bg-red-600 px-4 py-2 text-sm"
          >
            取消
          </button>
        ) : (
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="rounded-md bg-sky-700 hover:bg-sky-600 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {hasHistory ? "发送" : "开始调研"}
          </button>
        )}
      </div>
      <p className="text-xs text-neutral-500 text-left">
        Ctrl + Enter 快速提交
      </p>
    </form>
  );
};
