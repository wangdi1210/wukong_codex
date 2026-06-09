# 小程序 UI 自动化 MVP

这是 UI 自动化平台的小程序首期工程，用于先跑通用例资产、执行编排、Driver 抽象和报告闭环。

## 安装

```bash
python -m pip install -e ".[test]"
```

## 执行 dry-run 冒烟用例

```bash
miniapp-ui-auto run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

## 用例模型

用例使用 YAML 编写，并通过 `schemas/case.schema.json` 校验。执行器消费标准动作，例如 `open_page`、`tap`、`input` 和断言动作。Minium 被封装在 Driver 层，后续 Web/App/API Driver 可以复用同一套编排和报告链路。
