(function attachRuleFormLogic(root) {
  const NEAR_BUDGET_ACTION = "NEAR_BUDGET_ROI_ADD_BUDGET";
  const HOURLY_ROI_GOAL_ACTION = "HOURLY_SPEND_INCREASE_ROI_GOAL";
  const STEP_ROI_ACTION = "SPEND_STEP_ROI_STOP";

  function num(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function baseValues(values) {
    return {
      ...values,
      afterMinutes: num(values.afterMinutes),
      minSpend: num(values.minSpend),
      hourlySpendAbove: num(values.hourlySpendAbove),
      spendStep: num(values.spendStep),
      delayMinutes: num(values.delayMinutes),
      roiBelow: num(values.roiBelow),
      roiAbove: num(values.roiAbove),
      budgetRemainingPercent: num(values.budgetRemainingPercent),
      roiGoalIncrement: num(values.roiGoalIncrement),
      maxRoiGoal: num(values.maxRoiGoal),
      holdMinutes: num(values.holdMinutes),
      cooldown: num(values.cooldown),
      budgetValue: num(values.budgetValue),
      dailyCap: num(values.dailyCap),
      budgetMode: values.budgetMode || "fixed",
    };
  }

  function normalizeRuleFormValues(values = {}) {
    const action = values.action || "DISABLE";
    const result = baseValues({ ...values, action });

    if (action === STEP_ROI_ACTION) {
      result.afterMinutes = 0;
      result.minSpend = 0;
      result.hourlySpendAbove = 0;
      result.spendStep = result.spendStep > 0 ? result.spendStep : 100;
      result.delayMinutes = result.delayMinutes > 0 ? result.delayMinutes : 10;
      result.roiAbove = 0;
      result.budgetRemainingPercent = 0;
      result.roiGoalIncrement = 0;
      result.maxRoiGoal = 0;
      result.holdMinutes = 0;
      result.cooldown = 0;
      result.budgetMode = "fixed";
      result.budgetValue = 0;
      result.dailyCap = 0;
      return result;
    }

    if (action === NEAR_BUDGET_ACTION) {
      result.afterMinutes = 0;
      result.minSpend = 0;
      result.hourlySpendAbove = 0;
      result.spendStep = 0;
      result.delayMinutes = 0;
      result.roiBelow = 0;
      result.budgetRemainingPercent = result.budgetRemainingPercent > 0 ? result.budgetRemainingPercent : 10;
      result.roiAbove = result.roiAbove > 0 ? result.roiAbove : 2.2;
      result.roiGoalIncrement = 0;
      result.maxRoiGoal = 0;
      result.holdMinutes = 0;
      result.cooldown = 0;
      result.budgetMode = "fixed";
      result.budgetValue = result.budgetValue > 0 ? result.budgetValue : 100;
      result.dailyCap = 0;
      return result;
    }

    if (action === HOURLY_ROI_GOAL_ACTION) {
      result.afterMinutes = 0;
      result.minSpend = 0;
      result.hourlySpendAbove = result.hourlySpendAbove > 0 ? result.hourlySpendAbove : 100;
      result.spendStep = 0;
      result.delayMinutes = 0;
      result.roiBelow = 0;
      result.roiAbove = 0;
      result.budgetRemainingPercent = 0;
      result.roiGoalIncrement = result.roiGoalIncrement > 0 ? result.roiGoalIncrement : 0.2;
      result.maxRoiGoal = result.maxRoiGoal > 0 ? result.maxRoiGoal : 2.4;
      result.holdMinutes = 0;
      result.cooldown = 0;
      result.budgetMode = "fixed";
      result.budgetValue = 0;
      result.dailyCap = 0;
      return result;
    }

    result.hourlySpendAbove = 0;
    result.spendStep = 0;
    result.delayMinutes = result.delayMinutes > 0 ? result.delayMinutes : 10;
    result.budgetRemainingPercent = 0;
    result.roiGoalIncrement = 0;
    result.maxRoiGoal = 0;
    result.holdMinutes = 0;
    result.cooldown = 0;
    result.dailyCap = 0;
    if (action === "DISABLE" || action === "NOTIFY") {
      result.roiAbove = 0;
      result.budgetMode = "fixed";
      result.budgetValue = 0;
    }
    return result;
  }

  function defaultRuleForGroup(groupId, createdAt, controlPlanSmartBidTypes = ["SMART_BID_CUSTOM"]) {
    const common = {
      id: "",
      groupId: groupId || "risk-stop",
      createdAt,
      enabled: false,
      shopIds: [],
      planPrefixes: [],
      planSmartBidTypes: [...controlPlanSmartBidTypes],
      notify: "wechat",
    };
    if (groupId === "scale-budget") {
      return {
        ...common,
        name: "预算将尽高 ROI 继续加",
        action: NEAR_BUDGET_ACTION,
        ...normalizeRuleFormValues({
          action: NEAR_BUDGET_ACTION,
          budgetRemainingPercent: 10,
          roiAbove: 2.2,
          budgetValue: 100,
        }),
      };
    }
    if (groupId === "watch-notify") {
      return {
        ...common,
        name: "零成交提醒",
        action: "NOTIFY",
        ...normalizeRuleFormValues({
          action: "NOTIFY",
          afterMinutes: 90,
          minSpend: 180,
          roiBelow: 0.1,
        }),
      };
    }
    return {
      ...common,
      name: "低 ROI 自动暂停",
      action: "DISABLE",
      ...normalizeRuleFormValues({
        action: "DISABLE",
        afterMinutes: 60,
        minSpend: 90,
        roiBelow: 1.3,
      }),
    };
  }

  const api = {
    defaultRuleForGroup,
    normalizeRuleFormValues,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QianchuanRuleFormLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
