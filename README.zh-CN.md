# 千川自动化投放控制台

这是一个面向巨量千川投放团队的本地优先自动化系统。它把计划列表、报表缓存、规则执行、操作审计和只读分析接口放在一套可部署的工具里，帮助运营团队把重复判断变成可追踪的规则。

这个公开仓库已经脱敏。仓库里没有生产数据库、真实报表、访问令牌、刷新令牌、API key、Webhook、内网地址、店铺 ID、广告主 ID、员工姓名或本地管理员密码。

## 适合谁

- 每天需要管理大量千川计划的投放团队
- 希望把低 ROI 停投、优秀计划加预算、预算归位、商品维度停投做成规则的人
- 需要保留操作日志、API 调用日志和复盘证据的团队
- 想让 coding agent 分析投放报表，又不希望它接触写入接口的人

## 系统做什么

- 本地控制台：查看计划、规则、报表、操作日志
- 本地代理：保存快照、缓存报表、执行规则、记录审计
- OAuth/API broker：承接巨量引擎授权、刷新 token、代理千川 API
- 只读 MCP：让 agent 读取报表和动作日志，用于复盘和代码维护

目录结构：

```text
qianchuan-control-frontend/   静态投放控制台
qianchuan-local-control/      本地代理、SQLite 缓存、规则调度、审计日志
qianchuan-oauth-deploy/       OAuth 回调和千川 API broker
qianchuan-report-mcp/         只读报表 MCP
docs/                         架构、安全、投放方法论
scripts/                      脱敏和检查脚本
```

## 投放思路

千川自动化要先把计划拆成几类，再给每类计划设置不同的观察窗口和动作边界。常见分层：

- 冷启动计划：看点击、成交、消耗速度，先保留样本，不急着大幅调预算
- 放量计划：ROI、成交量、消耗节奏都达标时，按阶梯加预算
- 控成本计划：预算更保守，重点看 ROI 下限和亏损速度
- 恢复计划：曾经停投或降预算的计划，先小预算观察，再决定是否恢复
- 商品观察池：按商品聚合所有计划，避免同一个商品在多个计划里连续亏损

更多细节见 [docs/zh-CN/qianchuan-playbook.md](docs/zh-CN/qianchuan-playbook.md)。

## 可复用规则库

公开版提供一套示例规则，所有阈值都需要按行业、客单价、毛利和履约成本调整：

- 低 ROI 暂停
- 高 ROI 阶梯加预算
- 日预算归位
- 无成交消耗止损
- 商品连续亏损停投
- 异常消耗预警
- 暂停后恢复观察

规则模板见 [docs/zh-CN/rule-library.md](docs/zh-CN/rule-library.md)。

## 本地检查

核心检查不需要额外安装 Python 包：

```powershell
python .\scripts\public_safety_scan.py .
python -m py_compile .\qianchuan-local-control\local_control.py
python -m py_compile .\qianchuan-oauth-deploy\app.py
python -m py_compile .\qianchuan-report-mcp\server.py
node --check .\qianchuan-control-frontend\app.js
node .\qianchuan-control-frontend\test_rule_form_logic.cjs
```

运行前复制示例配置，并填入你自己的授权信息：

```powershell
Copy-Item .\qianchuan-local-control\local.secrets.example.ps1 .\qianchuan-local-control\local.secrets.ps1
Copy-Item .\qianchuan-local-control\admin.local.example.txt .\qianchuan-local-control\admin.local.txt
Copy-Item .\qianchuan-oauth-deploy\qianchuan-oauth.env.example .\qianchuan-oauth-deploy\qianchuan-oauth.env
```

这些本地文件已被 `.gitignore` 排除，发布前仍建议运行脱敏扫描。

## 安全边界

- 浏览器前端不保存管理员 token
- 写入动作必须走受控 API 和审计日志
- MCP 只读读取报表，不开放预算、暂停、启用、用户管理或 token 读取能力
- 公开文档只保留方法和示例阈值
- 生产报表和业务标识留在本地环境

详细说明见 [docs/security.md](docs/security.md)。

