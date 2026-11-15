import { InputForm } from "./InputForm";

interface WelcomeScreenProps {
  handleSubmit: (
    submittedInputValue: string,
    effort: string,
    model: string
  ) => void;
  onCancel: () => void;
  isLoading: boolean;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  handleSubmit,
  onCancel,
  isLoading,
}) => (
  <div className="h-full flex flex-col items-center justify-center text-center px-4 flex-1 w-full max-w-3xl mx-auto gap-4">
    <div>
      <h1 className="text-4xl md:text-5xl font-semibold text-neutral-100 mb-3">
        医药投资深度研究工作台
      </h1>
      <p className="text-lg md:text-xl text-neutral-400">
        输入调研主题，系统自动完成公开信息检索、整理与初稿撰写；所有结论均需人工复核，不构成投资建议
      </p>
    </div>
    <div className="w-full mt-4">
      <InputForm
        onSubmit={handleSubmit}
        isLoading={isLoading}
        onCancel={onCancel}
        hasHistory={false}
      />
    </div>
    <p className="text-xs text-neutral-500">
      基于 LLM 的医药深度研究 · 仅使用公开信息 · 国内信源经阿里百炼检索，海外信源经 Firecrawl 检索
    </p>
  </div>
);
