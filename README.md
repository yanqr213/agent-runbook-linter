# agent-runbook-linter

`agent-runbook-linter` 是一个离线 CLI，用来扫描仓库中的 AI 编程代理指令文件，例如 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`CODEX/CODEX.md`、`.cursor/rules` 以及包含 agent/runbook 指令的 `README`。它会发现冲突、缺失、不可执行或风险过高的指令，并输出 Markdown、JSON、JUnit 或 SARIF 报告，适合作为 CI gate。

它面向正在使用 Codex、Claude Code、Cursor、Aider 等 AI coding agents 的开发者和团队。目标不是替代人工 review，而是在代理执行前尽早暴露会让任务跑偏、越权或无法验收的 runbook 问题。

## 主要功能

- 自动发现常见 agent 指令文件和 README 中的 runbook 内容。
- 检测互相矛盾的命令和包管理器，例如同时要求 `npm`、`pnpm`、`yarn`。
- 检测测试命令缺失、验收标准缺失、交付要求模糊。
- 检测环境变量或 secret 暴露风险、过度授权、允许/禁止规则冲突。
- 检测不存在的本地路径、过长上下文、过期命令、语言/地区化提示缺失。
- 支持 JSON 配置，YAML 配置可选；未安装 PyYAML 时支持简单顶层 YAML fallback。
- 支持忽略项、规则 severity、`--check warning|error`、`--output` 自动创建父目录。
- 输出 `markdown`、`json`、`junit`、`sarif`，可直接接入 CI 和 GitHub Code Scanning。

## 安装

本地开发或 CI 中推荐从源码安装：

```bash
python -m pip install -e .
```

发布到包索引后可安装：

```bash
python -m pip install agent-runbook-linter
```

Python 版本要求：3.9 或更高。运行时不强制依赖第三方包。

## 基本用法

扫描当前仓库并输出 Markdown：

```bash
agent-runbook-linter .
```

输出 JSON 到文件，父目录会自动创建：

```bash
agent-runbook-linter . --format json --output reports/agent-runbook.json
```

发现 warning 及以上即失败：

```bash
agent-runbook-linter . --check warning
```

发现 error 才失败：

```bash
agent-runbook-linter . --check error
```

使用配置文件：

```bash
agent-runbook-linter . --config agent-runbook-linter.json --format junit --output reports/junit.xml
```

输出 SARIF：

```bash
agent-runbook-linter . --format sarif --output reports/agent-runbook.sarif
```

也可以用模块方式运行：

```bash
python -m agent_runbook_linter examples/problem-repo --format markdown
```

## 输出示例

Markdown 示例：

```markdown
# Agent Runbook Linter Report

- Documents scanned: `1`
- Findings: `3`
- Severity counts: error `2`, warning `1`, info `0`

## Findings

- **ERROR** `missing-test-command` at `AGENTS.md:1`
  No executable test command was found in agent instructions.
```

JSON 示例：

```json
{
  "tool": "agent-runbook-linter",
  "summary": {
    "documents": 1,
    "findings": 1,
    "counts": {
      "info": 0,
      "warning": 0,
      "error": 1
    }
  },
  "findings": [
    {
      "rule_id": "missing-test-command",
      "severity": "error",
      "message": "No executable test command was found in agent instructions.",
      "path": "AGENTS.md",
      "line": 1,
      "details": {}
    }
  ]
}
```

JUnit 输出适合 CI 系统展示为测试失败，每个 finding 会成为一个 failing testcase。SARIF 输出遵循 2.1.0 结构，可上传到 GitHub Code Scanning，把 runbook 问题显示在 PR 的扫描视图里。

## 规则配置

默认会自动读取以下文件之一：

- `.agent-runbook-linter.json`
- `agent-runbook-linter.json`
- `.agent-runbook-linter.yaml`
- `.agent-runbook-linter.yml`

JSON 配置示例：

```json
{
  "include": ["AGENTS.md", "CLAUDE.md", "CODEX/CODEX.md", ".cursor/rules/**", "README.md"],
  "exclude": [".git/**", "node_modules/**", "dist/**"],
  "max_context_lines": 180,
  "require_locale_hint": true,
  "locale_terms": ["language", "locale", "中文", "英文"],
  "rules": {
    "missing-test-command": {
      "severity": "error"
    },
    "missing-locale-hint": {
      "severity": "warning"
    },
    "long-context": {
      "severity": "info",
      "options": {
        "note": "Track oversized instructions without blocking builds."
      }
    }
  },
  "ignore": [
    {
      "rule": "missing-path",
      "path": "README.md"
    },
    {
      "rule": ["vague-delivery", "long-context"],
      "path": "CLAUDE.md",
      "line": 12
    }
  ]
}
```

规则可设置：

- `enabled`: `true` 或 `false`
- `severity`: `info`、`warning`、`error`
- `options`: 预留给未来更细粒度的规则参数

忽略项支持按 `rule`、`path` glob、`line` 匹配。`rule` 可为字符串、数组或 `*`。

## 检测规则

| Rule ID | 说明 |
| --- | --- |
| `conflicting-package-managers` | 同一语言生态中出现多个未说明优先级的包管理器 |
| `conflicting-commands` | 同一用途出现多个命令但没有明确选择规则 |
| `missing-test-command` | 未发现可执行测试命令 |
| `secret-exposure-risk` | 指令疑似包含真实 token、password、secret 或 API key |
| `excessive-permission` | 要求过度权限、跳过审批或关闭 sandbox |
| `allow-deny-conflict` | 同一动作同时被允许和禁止 |
| `missing-path` | 指令引用的仓库内路径不存在 |
| `long-context` | 指令文件过长，可能降低 agent 执行稳定性 |
| `missing-acceptance-criteria` | 缺少验收标准、验证步骤或预期输出 |
| `missing-locale-hint` | 缺少回复语言、地区化或本地化要求 |
| `stale-command` | 引用常见过期命令或工具 |
| `vague-delivery` | 交付要求过于模糊 |

## CI 示例

GitHub Actions：

```yaml
name: Agent Runbook Lint

on:
  pull_request:
  push:
    branches: ["main"]

jobs:
  lint-runbooks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install agent-runbook-linter
      - run: agent-runbook-linter . --check warning --format junit --output reports/agent-runbook-junit.xml
```

上传 SARIF 到 GitHub Code Scanning：

```yaml
- run: agent-runbook-linter . --format sarif --output reports/agent-runbook.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: reports/agent-runbook.sarif
```

如果从源码仓库运行：

```bash
python -m pip install -e .
agent-runbook-linter . --check error --format markdown --output reports/agent-runbook.md
```

## 适用场景

- 团队同时使用多个 AI coding agent，需要统一仓库级操作约束。
- PR 中修改了 `AGENTS.md`、`CLAUDE.md`、`.cursor/rules` 或 README，希望自动检查。
- 想避免 agent 在没有测试命令、验收标准或语言要求时交付不可验证结果。
- 希望在 CI 中阻止过度授权、secret 泄露和路径失效的 runbook。

## 限制

- 当前规则是静态启发式，不会执行命令，也不会联网校验工具版本。
- “冲突”和“过期命令”判断无法覆盖所有技术栈，需要团队用配置和 ignore 调整。
- YAML fallback 只支持简单顶层标量和列表；复杂嵌套 YAML 请安装 `PyYAML` 或使用 JSON。
- README 只在包含 agent、runbook、Codex、Claude Code、Cursor、Aider 等相关标记时扫描。

## English Overview

`agent-runbook-linter` is an offline CLI for linting AI coding agent instructions in files such as `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `CODEX/CODEX.md`, `.cursor/rules`, and agent-related README content. It detects contradictory commands, missing test and validation steps, unsafe permission grants, secret exposure risks, missing paths, long context, vague delivery instructions, and missing language or locale guidance.

It is designed for developers using Codex, Claude Code, Cursor, Aider, and similar tools. Reports are available as Markdown, JSON, JUnit, or SARIF, making the linter suitable for CI gates and GitHub Code Scanning.

Basic usage:

```bash
agent-runbook-linter . --check warning --format json --output reports/agent-runbook.json
agent-runbook-linter . --format sarif --output reports/agent-runbook.sarif
```

The tool is intentionally conservative and dependency-light. It does not execute commands or send repository content to external services.
