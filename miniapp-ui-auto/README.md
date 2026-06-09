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

## 用自然语言生成用例

```bash
python -m miniapp_ui_auto.cli generate `
  --case-id miniapp_login_generated_001 `
  --title 手机号验证码登录成功 `
  --module login `
  --tag smoke `
  --tag ai-generated `
  --output cases/smoke/miniapp_login_generated_001.yaml `
  --text "打开 pages/index/index。点击 我的。点击 登录。输入 手机号输入框：13800000000。输入 验证码输入框：123456。点击 确认登录。断言 用户昵称"
```

生成命令会把自然语言步骤转换成 YAML，并立即用 `schemas/case.schema.json` 校验。生成后可以直接执行：

```bash
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag ai-generated --report-dir reports/summary
```

## 用例模型

用例使用 YAML 编写，并通过 `schemas/case.schema.json` 校验。执行器消费标准动作，例如 `open_page`、`tap`、`input` 和断言动作。Minium 被封装在 Driver 层，后续 Web/App/API Driver 可以复用同一套编排和报告链路。

## 本地验证

```bash
python -m pytest -v
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

dry-run 命令会写出 `reports/summary/summary.json`。
