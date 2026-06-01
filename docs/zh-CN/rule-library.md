# 千川自动化规则库模板

这里给一组公开可复用的规则模板。示例阈值只用于说明规则结构，落地前要按行业、毛利、履约成本和投放阶段调整。

## 规则字段建议

每条规则建议包含这些字段：

```text
name              规则名称
scope             计划级、商品级、账户级
condition         触发条件
action            暂停、加预算、归位、提醒
afterMinutes      最短观察时间
cooldownMinutes   动作冷却时间
dailyCap          单日最多动作次数
hold              人工保护标记
reasonTemplate    写入日志的原因模板
```

## 一、低 ROI 暂停

用途：控制亏损，适合控成本计划和冷启动观察结束后的计划。

```text
scope: plan
condition:
  spend >= sample_spend_floor
  roi < target_roi_floor
  running_minutes >= afterMinutes
  hold != true
action:
  pause_plan
guard:
  pause action ends this plan's current rule run
log:
  plan, spend, roi, running_minutes, rule_name
```

示例口径：

- `afterMinutes`: 30 到 90
- `sample_spend_floor`: 按商品毛利和客单价设置
- `target_roi_floor`: 按团队盈亏线设置

## 二、高 ROI 阶梯加预算

用途：放大表现稳定的计划。

```text
scope: plan
condition:
  roi >= scale_roi_line
  orders >= min_orders
  spend_rate is stable
  last_budget_action_minutes >= cooldownMinutes
  today_budget_increase_count < dailyCap
action:
  add_budget_by_step
guard:
  skip if plan is paused
  skip if current budget already reached daily ceiling
log:
  old_budget, new_budget, roi, orders, spend
```

示例口径：

- 每次加预算用固定步长
- 每天限制次数
- 每次动作后进入冷却

## 三、无成交消耗止损

用途：防止计划持续花费但没有成交。

```text
scope: plan
condition:
  spend >= no_order_spend_floor
  orders == 0
  running_minutes >= afterMinutes
action:
  pause_plan
guard:
  skip if plan has manual hold
log:
  spend, clicks, running_minutes
```

适合冷启动和新素材测试。阈值要结合客单价，客单价高的类目需要更长观察窗口。

## 四、日预算归位

用途：每天把计划预算拉回可控起点，便于第二天重新观察。

```text
scope: plan
schedule:
  once per day
condition:
  plan is active
  target_budget exists for plan type
  abs(current_budget - target_budget) >= platform_min_change
action:
  set_budget(target_budget)
guard:
  skip paused plans
  skip changes below platform_min_change
log:
  current_budget, target_budget, skipped_reason
```

建议把不同计划类型拆开，例如放量计划、控成本计划、恢复计划分别设置目标预算。

## 五、商品连续亏损停投

用途：按商品聚合风险，避免同一商品在多个计划里继续亏损。

```text
scope: product
condition:
  product_spend >= product_sample_floor
  product_roi < product_roi_floor
  losing_days >= min_losing_days
action:
  pause_related_plans
guard:
  exclude manually protected plans
log:
  product_name_hash, related_plan_count, product_spend, product_roi
```

公开实现里可以用商品名 hash 或脱敏商品名写日志。生产环境可以保留完整商品字段，但不要推到公开仓库。

## 六、异常消耗预警

用途：发现预算快速消耗、转化异常或接口异常。

```text
scope: plan
condition:
  spend_rate >= spend_rate_alert_line
  orders below expected range
action:
  notify_only
guard:
  no write action
log:
  spend_rate, orders, clicks
```

这类规则先做提醒，等人工确认后再决定是否停投或调预算。

## 七、暂停后恢复观察

用途：让被暂停的计划有小流量复测机会。

```text
scope: plan
condition:
  plan was paused by automation
  latest product status is allowed
  recovery_window is open
action:
  enable_plan_with_low_budget
guard:
  require admin confirmation
  no automatic budget increase during recovery window
log:
  previous_pause_reason, recovery_budget, recovery_window
```

恢复动作建议默认需要人工确认。恢复后先观察成交和 ROI，再决定是否放回正常规则池。

## 八、规则上线清单

上线前逐项检查：

- 规则有名称和负责人
- 阈值来自可解释的经营口径
- 触发条件包含观察窗口
- 写入动作有冷却时间
- 暂停动作优先级高于加预算
- 每条动作都写日志
- 平台拒绝和跳过原因能被复盘
- 人工保护标记能阻止自动动作
- 生产 token 没有进入前端和公开文档

## 九、复盘口径

每周可以按规则维度看效果：

- 触发次数
- 成功次数
- 跳过次数
- 平台拒绝次数
- 误伤计划数
- 节省人工操作次数
- 减少亏损消耗
- 放量带来的新增成交

这些指标能帮助团队调整阈值，也能判断哪条规则值得继续保留。

