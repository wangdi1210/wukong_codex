# 小程序 UI 自动化 MVP

这是 UI 自动化平台的小程序首期工程，用于先跑通用例资产、执行编排、Driver 抽象和报告闭环。当前主路线是 **Airtest/Poco 优先**，适合没有小程序源码、只能像真实用户一样操作微信小程序的场景；Minium 仅作为拿到小程序源码和开发者工具权限时的可选 Driver。

## 安装

```bash
python -m pip install -e ".[test]"
```

## 执行 dry-run 冒烟用例

```bash
miniapp-ui-auto run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

`--driver dry-run` 表示用本地空驱动验证用例和报告链路。真实设备执行时再改为：

```bash
miniapp-ui-auto run --cases cases --driver airtest --tag smoke --report-dir reports/summary
```

## 配置 Airtest/Poco

真实设备执行前，先配置 `config/airtest.yaml`：

```yaml
airtest:
  device_uri: "Android:///127.0.0.1:7555"
  package: com.tencent.mm
  miniapp_name: 职悟空
  image_threshold: 0.8
  image_dir: assets/images
  poco:
    enabled: true
```

说明：

- `device_uri` 是 Airtest 设备地址，可以是 Android 真机、模拟器或 iOS 设备。
- `package` 默认是微信 Android 包名 `com.tencent.mm`。
- `miniapp_name` 是目标小程序名。
- `poco.enabled: true` 时优先通过控件文本点击和断言。
- `assets/images` 用于保存图片模板，例如 `确认登录.png`。当 Poco 找不到控件或页面不可识别时，Driver 会使用图片模板。

真实执行命令：

```bash
python -m miniapp_ui_auto.cli run --cases cases --driver airtest --tag smoke --report-dir reports/summary
```

当前 `open_miniapp` 已预留 Poco 文本入口。不同团队进入微信小程序的路径可能不同，后续可以把“搜索小程序、最近使用、扫码入口”等路径沉淀成项目级步骤或模板。

## 用自然语言生成用例

```bash
python -m miniapp_ui_auto.cli generate `
  --case-id miniapp_login_generated_001 `
  --title 手机号验证码登录成功 `
  --module login `
  --tag smoke `
  --tag ai-generated `
  --output cases/smoke/miniapp_login_generated_001.yaml `
  --text "打开 微信。进入 职悟空小程序。点击 我的。点击 登录。输入 手机号输入框：13800000000。输入 验证码输入框：123456。点击 确认登录。断言 用户昵称"
```

生成命令会把自然语言步骤转换成 YAML，并立即用 `schemas/case.schema.json` 校验。生成后可以直接执行：

```bash
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag ai-generated --report-dir reports/summary
```

## 用例模型

用例使用 YAML 编写，并通过 `schemas/case.schema.json` 校验。执行器消费标准动作，例如 `open_app`、`open_miniapp`、`tap`、`input` 和断言动作。Airtest/Poco 被封装在 Driver 层，后续 Minium/Web/App/API Driver 可以复用同一套编排和报告链路。

## 本地验证

```bash
python -m pytest -v
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

dry-run 命令会写出 `reports/summary/summary.json`。
