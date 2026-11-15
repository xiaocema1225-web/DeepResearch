import ReactMarkdown from "react-markdown";
import { ActivityTimeline } from "./ActivityTimeline";
import { cn } from "../lib/utils";

interface Message {
  type: string;
  content: string | unknown;
  id?: string;
}

interface ChatMessagesViewProps {
  messages: Message[];
  isLoading: boolean;
  nodeEvents: string[];
  /** 是否处于"计划待确认"状态（PRD 8.5：确认前不得检索） */
  awaitingConfirmation: boolean;
  onConfirmPlan: () => void;
  onNewTopic: () => void;
}

function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content))
    return content
      .map((c) => (typeof c === "string" ? c : (c as any)?.text ?? ""))
      .join("");
  return String(content ?? "");
}

export const ChatMessagesView: React.FC<ChatMessagesViewProps> = ({
  messages,
  isLoading,
  nodeEvents,
  awaitingConfirmation,
  onConfirmPlan,
  onNewTopic,
}) => {
  const lastAiIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].type === "ai") return i;
    }
    return -1;
  })();

  return (
    <div className="flex flex-col gap-4 w-full max-w-3xl mx-auto px-4 py-6">
      {messages.map((msg, idx) => {
        const isUser = msg.type === "human";
        const isLastAi = idx === lastAiIdx;
        return (
          <div key={msg.id ?? idx}>
            {/* AI 消息上方挂活动时间线（进行中自动展开） */}
            {!isUser && isLastAi && (
              <ActivityTimeline events={nodeEvents} isLoading={isLoading} />
            )}
            <div
              className={cn(
                "rounded-xl px-4 py-3 text-sm leading-6",
                isUser
                  ? "bg-sky-800/60 ml-auto max-w-[85%]"
                  : "bg-neutral-800 mr-auto max-w-full"
              )}
            >
              {isUser ? (
                <p className="whitespace-pre-wrap">{messageText(msg.content)}</p>
              ) : (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sky-400 underline"
                        >
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {messageText(msg.content)}
                  </ReactMarkdown>
                </div>
              )}
              {/* 每条 AI 消息带复制按钮（PRD 8.7） */}
              {!isUser && (
                <button
                  className="mt-2 text-xs text-neutral-400 hover:text-neutral-200"
                  onClick={() =>
                    navigator.clipboard.writeText(messageText(msg.content))
                  }
                >
                  复制
                </button>
              )}
            </div>
            {/* 计划待确认状态：提示 + 需求确认按钮（PRD 6.2/8.5） */}
            {!isUser && isLastAi && awaitingConfirmation && !isLoading && (
              <div className="mt-3 rounded-lg border border-amber-600/50 bg-amber-900/20 px-4 py-3">
                <p className="text-sm text-amber-200 mb-2">
                  确认以上调研方向后，点击"需求确认"开始深度检索（确认前系统不会执行检索）
                </p>
                <button
                  onClick={onConfirmPlan}
                  className="rounded-md bg-amber-600 hover:bg-amber-500 px-4 py-2 text-sm text-white"
                >
                  需求确认
                </button>
              </div>
            )}
          </div>
        );
      })}

      {messages.length > 0 && !isLoading && (
        <button
          onClick={onNewTopic}
          className="self-center mt-2 rounded-md border border-neutral-600 px-4 py-2 text-sm text-neutral-300 hover:bg-neutral-800"
        >
          发起新调研
        </button>
      )}
    </div>
  );
};
