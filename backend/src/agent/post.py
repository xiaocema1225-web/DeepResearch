import re

class Post:
    @staticmethod
    def extract_pattern(text, pattern):
        pattern = re.compile(f"```{pattern}\s(.*?)```", re.DOTALL)
        matches = pattern.findall(text)
        return matches[0] if matches else text


if __name__ == "__main__":
    text = """```markdown
# 需求清晰度进度条: 60%

## 核心需求理解：
1. **核心目标**: 分析某医药赛道的竞争格局

## 下一步：
如需求清晰明了，请回复【需求确认】，我将进行报告生成任务，如果还存在问题，请直接说明。
```
"""
    output = Post.extract_pattern(text, "markdown")
    print(output)
