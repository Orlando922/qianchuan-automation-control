const assert = require("node:assert/strict");
const test = require("node:test");

const {
  defaultRuleForGroup,
  normalizeRuleFormValues,
} = require("./rule-form-logic.js");

test("risk-stop new rule defaults to low ROI pause without stale hourly values", () => {
  const rule = defaultRuleForGroup("risk-stop", "2026-05-22T00:00:00.000Z", ["SMART_BID_CUSTOM"]);

  assert.equal(rule.action, "DISABLE");
  assert.equal(rule.name, "低 ROI 自动暂停");
  assert.equal(rule.hourlySpendAbove, 0);
  assert.equal(rule.delayMinutes, 10);
  assert.equal(rule.spendStep, 0);
});

test("disable rule form clears values that belong to hourly ROI goal rules", () => {
  const values = normalizeRuleFormValues({
    action: "DISABLE",
    afterMinutes: 60,
    minSpend: 90,
    hourlySpendAbove: 100,
    spendStep: 0,
    delayMinutes: 0,
    roiBelow: 1.8,
    roiAbove: 0,
    budgetRemainingPercent: 0,
    roiGoalIncrement: 0.2,
    maxRoiGoal: 2.4,
    holdMinutes: 0,
    cooldown: 0,
    budgetMode: "fixed",
    budgetValue: 0,
    dailyCap: 0,
  });

  assert.equal(values.hourlySpendAbove, 0);
  assert.equal(values.delayMinutes, 10);
  assert.equal(values.roiGoalIncrement, 0);
  assert.equal(values.maxRoiGoal, 0);
  assert.equal(values.holdMinutes, 0);
  assert.equal(values.cooldown, 0);
  assert.equal(values.budgetValue, 0);
  assert.equal(values.dailyCap, 0);
});

test("step ROI rule keeps the 10 minute delay default", () => {
  const values = normalizeRuleFormValues({
    action: "SPEND_STEP_ROI_STOP",
    spendStep: 0,
    delayMinutes: 0,
    roiBelow: 1.2,
  });

  assert.equal(values.spendStep, 100);
  assert.equal(values.delayMinutes, 10);
  assert.equal(values.hourlySpendAbove, 0);
});

test("add budget rule keeps only fields used by the backend", () => {
  const values = normalizeRuleFormValues({
    action: "ADD_BUDGET",
    afterMinutes: 60,
    minSpend: 200,
    roiAbove: 2,
    budgetMode: "fixed",
    budgetValue: 100,
    holdMinutes: 30,
    cooldown: 60,
    dailyCap: 500,
  });

  assert.equal(values.afterMinutes, 60);
  assert.equal(values.minSpend, 200);
  assert.equal(values.roiAbove, 2);
  assert.equal(values.budgetValue, 100);
  assert.equal(values.holdMinutes, 0);
  assert.equal(values.cooldown, 0);
  assert.equal(values.dailyCap, 0);
});
