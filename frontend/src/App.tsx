import { useState, useCallback } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { ChatMessagesView } from "./components/ChatMessagesView";
import { InputForm } from "./components/InputForm";

/** 研究强度 → 查询数 / 反思循环数 / 固定模型（PRD 8.4 档位 + 按强度绑定模型，不可改选） */
const EFFORT_MAP: Record<
  string,
  { queries: number; loops: number; model: string }
> = {
  low: { queries: 1, loops: 1, model: "deepseek-v4.1-flash" },
  medium: { queries: 3, loops: 3, model: "qwen3.8-flash" },
  high: { queries: 5, loops: 10, model: "qwen3.8-max-0902" },
};

const API_URL =
  (import.meta as any).env?.VITE_API_URL ?? "http://localhost:2024";

export default function App() {
  const [nodeEvents, setNodeEvents] = useState<string[]>([]);

  const thread = useStream<{ messages: any[] }>({
    apiUrl: API_URL,
    assistantId: "agent",
    messagesKey: "messages",
    onUpdateEvent: (event: any) => {
      // 记录流式过程中的后端节点名，驱动活动时间线（PRD 8.6 过程可视化）
      if (event && typeof event === "object") {
        Object.keys(event).forEach((node) => {
          if (node !== "__end__" && node !== "awaiting_plan_confirmation") {
            setNodeEvents((prev) => [...prev, node]);
          }
        });
      }
    },
  });

  const isLoading = thread.isLoading;
  const messages = (thread.messages ?? []) as any[];

  // 计划待确认：已经生成了计划，但尚未进入检索阶段（PRD 8.5 人机协作关键点）
  const awaitingConfirmation =
    !isLoading &&
    messages.length > 0 &&
    nodeEvents.includes("generate_plan") &&
    !nodeEvents.includes("generate_search");

  const handleSubmit = useCallback(
    (inputValue: string, effort: string, model: string) => {
      const effortCfg = EFFORT_MAP[effort] ?? EFFORT_MAP.medium;
      setNodeEvents([]);
      thread.submit(
        {
          messages: [{ type: "human", content: inputValue }],
          initial_search_query_count: effortCfg.queries,
          max_research_loops: effortCfg.loops,
          // 模型由研究强度固定绑定（InputForm 已按档位传入）
          reasoning_model: model || effortCfg.model,
        } as any,
        { streamMode: ["values", "updates"] }
      );
    },
    [thread]
  );

  /** 用户点击"需求确认"：放行计划，开始检索（PRD 8.5：确认前系统不得检索） */
  const handleConfirmPlan = useCallback(() => {
    thread.submit(
      {
        messages: [{ type: "human", content: "需求确认" }],
        plan_status: "confirmed",
      } as any,
      { streamMode: ["values", "updates"] }
    );
  }, [thread]);

  /** 发起新调研：重置线程状态 */
  const handleNewTopic = useCallback(() => {
    window.open(window.location.href, "_blank");
  }, []);

  const hasHistory = messages.length > 0;

  return (
    <div className="flex flex-col h-screen bg-neutral-900">
      <main className="flex-1 overflow-y-auto flex flex-col">
        {!hasHistory ? (
          <WelcomeScreen
            handleSubmit={handleSubmit}
            onCancel={thread.stop}
            isLoading={isLoading}
          />
        ) : (
          <>
            <ChatMessagesView
              messages={messages}
              isLoading={isLoading}
              nodeEvents={nodeEvents}
              awaitingConfirmation={awaitingConfirmation}
              onConfirmPlan={handleConfirmPlan}
              onNewTopic={handleNewTopic}
            />
            <div className="sticky bottom-0 bg-neutral-900 border-t border-neutral-800 py-3">
              <div className="w-full max-w-3xl mx-auto px-4">
                <InputForm
                  onSubmit={handleSubmit}
                  isLoading={isLoading}
                  onCancel={thread.stop}
                  hasHistory={hasHistory}
                />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
