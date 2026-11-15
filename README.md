# AI Painpoint Generator (AI 痛点洞察生成器)

一个基于大模型流式输出（Streaming）的微型全栈应用。用户输入特定人群，AI 实时生成该人群的 3 个核心痛点，并给出一个可执行的 AI 解决方案。

## 技术栈
- **前端**: HTML5, Vanilla JavaScript (使用 ReadableStream 实现打字机效果)
- **后端**: Python (http.server, 代理请求解决跨域)
- **大模型**: DeepSeek API (流式输出)

## 运行方式
1. 启动后端服务: `python server.py`
2. 浏览器访问: `http://localhost:8000`
3. 输入你的 DeepSeek API Key

---
*This is my first step. The rest is being built.*
